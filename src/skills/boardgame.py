"""通用对弈 skill（说明书 + 怎么进入）+ 构造/注册。

说明书全程**不出现某一种棋的专有词**——走子由引擎决定、循环由行为树维持，LLM(说明书) 只负责：
解说、要不要认输/求和、听懂用户。换五子棋/围棋时换个适配器、配套 display_name/game_name 即可，instructions 一字不改。

launcher = "怎么在某个世界上起这局"：按大脑给的执方就座（take_seat）+ 配齐就开局 + 起对弈行为树。
orchestrator 只管调它、把"执哪方"当不透明 role 转交，自己不碰棋类细节（保持通用元控制器）。
"""
from __future__ import annotations

from .. import messages
from ..llm import LLM
from ..skill import Skill, SkillRegistry
from ..behavior.trees.boardgame import start_boardgame
from ..tools.boardgame import chess as _chess_tools  # noqa: F401  (import 即注册适配器)
from ..tools.boardgame.base import get_adapter

# 棋种无关的"对弈陪伴"说明书：走子是引擎的事，循环是行为树的事，你只管语言+高层判断。
PLAY_GAME_INSTRUCTIONS = """\
# 技能：对弈陪伴（play-a-game）—— 对弈行为树在对弈时按需把你叫出来
## 你的角色
你在陪用户下棋。**走哪一步由你自己的引擎决定**（行为树会自动用引擎看盘、走子、判轮次和终局），
你不挑棋、不算棋、不维持循环。你只负责三件"要用语言或高层判断"的事：
1. 解说：每走一手、或局势有变化时，用自然中文讲给用户听（走了什么、当前局势如何），简洁。
2. 解说认输：是否认输由对弈行为树按**引擎的形势评分**自动判定（你不心算棋）；当它判定认输/退出时，你把这个结果用一句话讲给用户听即可。
3. 听懂用户：用户在对弈框里说话时，判断他是想继续、悔棋、还是想退出（"不下了/认输/算了"=退出）。
## 铁律
- 你不假设是哪种棋；棋种差异由工具适配器处理，你只做语言和高层判断。
- 不要谎报棋步：以引擎实际走的、世界确认成功的那一手为准来解说。
- 语气像一个会讲解的棋手，简洁清楚。
"""


def _other(side: str) -> str:
    return "black" if side == "white" else "white"


def _controllers(world) -> dict:
    """读 world 给的角色 meta（perceive 的 state.controllers）：谁坐哪一席。读不到回 {}。"""
    try:
        return (world.perceive().state or {}).get("controllers") or {}
    except Exception:
        return {}


def _anima_seat(ctrl: dict) -> str | None:
    """从 controllers 里找出 **ANIMA 自己已就座** 的那一席（席位名直接来自世界的 controllers 键，
    不写死 white/black、不依赖单独的 seats 声明）。这是【读】ANIMA 已选的边，不替它选。"""
    return next((seat for seat, who in ctrl.items() if who == "anima"), None)


def _make_narrator(llm: LLM, skill: Skill):
    """解说回调 (uci, san, my_side)->一句话。游戏名从 skill.game_name 取（不再把"国际象棋"写死）；
    视角直接用 my_side（push 后翻面会算反）；不喂整盘 FEN（避免诱导 LLM 心算棋）。"""
    def narrate(uci, san, my_side):
        try:
            mover = messages.SIDE_NAMES.get(my_side, my_side)
            prompt = (f"你正在下{skill.game_name}，你执【{mover}】。你刚走的这一手用标准记谱是 {san}（{uci}）"
                      "——记谱里已注明走的是哪个子、到哪一格，请**以它为准**。\n"
                      "用一句口语话向用户复述这步走了什么（可带一点轻松语气）；"
                      "**不要编造你看不到的局势 / 子力位置 / 对手意图**，拿不准就只说这一手本身。只回这一句。")
            r = llm.chat(skill.instructions, [{"role": "user", "text": prompt}], [], None)
            return (r.text or "").strip() or messages.narrate_template(san, uci)
        except Exception:
            return messages.narrate_template(san, uci)
    return narrate


def _chess_launch(skill: Skill, world, llm: LLM, role: str | None = None) -> dict:
    """进入对弈技能 = 把【走子循环】交给引擎行为树。一步到位：能自己就座 + 开局就不再让用户分多步。

    role = 大脑想执的那一方（white/black），由 LLM 从对话理解后传进来（不是这里默认/写死——没传就只读已坐的）。
    流程：① 若还没就座且给了 role → 替它 take_seat(role)；② 若双方都配齐且还没开赛 → 顺手 start_game；
    ③ 起对弈行为树（树每拍跟着世界 phase 走：没开赛就空转等开始，开赛就下）。
    对手是谁由世界的 controllers 定（人在世界页配人/电脑，世界当权威）；这里不替对手配座、不假设是人是机。
    """
    adapter = get_adapter(skill.adapter_id)
    if adapter is None:
        return {"ok": False, "message": f"没有「{skill.adapter_id}」棋种适配器。"}

    # ① 还没就座且大脑给了执方 → 替它就座（take_seat 幂等：已坐也不报错）。
    ctrl = _controllers(world)
    my_side = _anima_seat(ctrl)
    if my_side is None and role:
        res = world.invoke("take_seat", seat=role)
        if not res.ok:
            return {"ok": False, "message": f"我想坐到「{role}」却没成：{res.message}"}
        ctrl = _controllers(world)
        my_side = _anima_seat(ctrl)
    if my_side is None:
        return {"ok": False, "message": "你想让我执哪一方（白/黑）？告诉我，我就座后直接开下。"}

    # ② 双方都配齐且还没开赛 → 顺手开局（对手得先在世界页配上人/电脑；没配齐就让树空转等开始）。
    opp = ctrl.get(_other(my_side))
    phase = (world.perceive().state or {}).get("phase")
    waiting_opponent = False
    if phase in ("not_start", "game_over"):
        if opp is not None:
            world.invoke("start_game")               # 失败也无妨：树会停在 not_start 等世界页点开始
        else:
            waiting_opponent = True                  # 对手席空着，进面板但先空转等人配对手

    # ③ 起行为树（执方此后由树每拍从 perceive 的 controllers 重读，不在脑里存死）。
    runner = start_boardgame(world, adapter, my_side,
                             narrate=_make_narrator(llm, skill), display_name=skill.display_name)
    side_cn = messages.SIDE_NAMES.get(my_side, my_side)
    if waiting_opponent:
        reply = f"我执{side_cn}就座了。对手席还空着——请在世界页给对手配上人/电脑并开始，我就开下。"
    else:
        # 开场白在 skill 这层拼（执方/对手是棋类专属概念，不上浮到通用 orchestrator）。
        reply = messages.game_start_reply(skill.display_name, side_cn[0] if side_cn else "", opp or "对手")
    return {"ok": True, "runner": runner, "display_name": skill.display_name, "reply": reply,
            "my_side": my_side, "opponent": opp or "对手"}


def _chess_chat_reply(message: str, run, llm: LLM) -> str:
    """对弈中闲聊：以对弈伙伴身份回一句。诚实：做不到的别假装能做。
    （从 orchestrator 搬下来——执方/手数这类任务专属状态只该在 skill 侧读，不污染通用主循环。）"""
    game = _chess_tools.ChessAdapter.name
    try:
        st = run.status()
        mover = messages.SIDE_NAMES.get(st.get("my_side", ""), "")
        sys = (f"你正在陪用户下{game}，是个轻松的对弈伙伴。用户在对局过程中跟你说话，用一句口语化的话回应即可。"
               "若他想悔棋/求和，而当前规则或世界并不支持，就如实说明做不到，别假装能做。")
        prompt = f"你执{mover}，已经走了 {st.get('move_count', 0)} 手。用户说：「{message}」。用一句话回应他。"
        r = llm.chat(sys, [{"role": "user", "text": prompt}], [], None)
        return (r.text or "").strip() or "嗯，我在呢，继续下。"
    except Exception:
        return "嗯，我在呢，继续下。"


def build_registry() -> SkillRegistry:
    """构造 skill 注册表（今天注册象棋；以后五子棋/围棋同样在这里加一行）。"""
    reg = SkillRegistry()
    reg.register(Skill(
        id=_chess_tools.ChessAdapter.id,                       # skill 身份与适配器 id 单一来源
        display_name="Chess Mode · 下棋模式",
        instructions=PLAY_GAME_INSTRUCTIONS,
        game_name=_chess_tools.ChessAdapter.name,              # "国际象棋"——单一来源在适配器
        required_action=_chess_tools.ChessAdapter.world_action,  # "move"——进入需世界提供的能力
        launcher=_chess_launch,
        adapter_id=_chess_tools.ChessAdapter.id,
        chat_reply=_chess_chat_reply,                          # 对弈中闲聊的搭话回调（任务专属，住在 skill 侧）
    ))
    return reg
