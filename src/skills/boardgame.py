"""下棋 skill 家族（大 skill 内含多个 sub-skill）+ 构造/注册。

新框架：世界只给画面 + 物理原语（move/remove/place），大脑当裁判、持信念、判轮次/终局。
所以「开局仪式」（就座/开始）不再塞进对弈——它要么是世界自己界面上的人类操作（如 sim-chess 网页），
要么是独立的 setup 子技能。下棋因此拆成一个家族，由用户聊天挑着组合：

- **play（对弈）**   ：进入时读一眼盘 seed 信念（自动支持半路接手），执方由 role 给；起对弈行为树。
- **record（记录）** ：读一次当前棋盘、汇报局面（查看/半路接手用）。
- **setup（摆盘）**  ：把目标局面用 place 摆到盘上（需世界支持 place，即物理世界）。

三者共享同一个 ChessAdapter（棋种规则单一来源）。orchestrator 只管：LLM 判意图→enter 某个 sub-skill→起 runner，
把「执哪方」当不透明 role 转交，自己不碰棋类细节。换五子棋/围棋 = 换适配器 + 在这里加同一组三行，instructions 不改。
"""
from __future__ import annotations

from .. import messages
from ..llm import LLM
from ..skill import Skill, SkillRegistry
from ..behavior.trees.boardgame import start_boardgame
from ..behavior.trees.boardtasks import start_record, start_setup
from ..tools.boardgame import chess as _chess_tools  # noqa: F401  (import 即注册适配器)
from ..tools.boardgame.base import get_adapter

# 棋种无关的"对弈陪伴"说明书：走子是引擎的事，循环是行为树的事，你只管语言+高层判断。
PLAY_GAME_INSTRUCTIONS = """\
# 技能：对弈陪伴（play-a-game）—— 对弈行为树在对弈时按需把你叫出来
## 你的角色
你在陪用户下棋。**走哪一步由你自己的引擎决定**（行为树会自动看盘、走子、判轮次和终局），
你不挑棋、不算棋、不维持循环。你只负责三件"要用语言或高层判断"的事：
1. 解说：每走一手、或局势有变化时，用自然中文讲给用户听（走了什么、当前局势如何），简洁。
2. 解说认输：是否认输由对弈行为树按**引擎的形势评分**自动判定（你不心算棋）；它判定认输/退出时，你一句话讲给用户听。
3. 听懂用户：用户在对弈框里说话时，判断他是想继续、悔棋、还是想退出（"不下了/认输/算了"=退出）。
## 铁律
- 你不假设是哪种棋；棋种差异由工具适配器处理，你只做语言和高层判断。
- 不要谎报棋步：以引擎实际走的、世界确认成功的那一手为准来解说。
- 语气像一个会讲解的棋手，简洁清楚。
"""

RECORD_BOARD_INSTRUCTIONS = """\
# 技能：记录棋盘（record-board）
你负责把「当前棋盘上的局面」看一眼、记录下来讲给用户（半路接手一盘棋、或用户想确认现在的局面时用）。
识别由视觉工具做，你只把结果用一句自然中文复述；识别不到就如实说看不清，别编。
"""

SETUP_BOARD_INSTRUCTIONS = """\
# 技能：摆盘（setup-board）
你负责把棋子按目标局面（默认标准开局）摆到盘上——机械臂逐个把子放到位。
摆放由行为树逐个执行，你只在完成/出问题时用一句话告诉用户。不假设棋种。
"""


def _make_narrator(llm: LLM, skill: Skill):
    """解说回调 (uci, san, my_side)->一句话。游戏名从 skill.game_name 取（不把棋种写死）；
    视角直接用 my_side；不喂整盘 FEN（避免诱导 LLM 心算棋）。"""
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


def _seed_belief(world, adapter):
    """进 play 时读一眼盘、从画面构造信念（半路接手 / 开局都走这条）。读不到 / 识别为空 → 退回标准开局。

    物理世界（gazebo）v0.4 还没视觉桥，识别不到会退回开局——那是预期（gazebo 的完整对弈=0.5）；
    数据世界（sim-chess）渲染盘认得出，进 play 即从当前盘接着下。
    """
    try:
        obs = world.perceive()
        if obs.image_png is not None:
            b = adapter.seed_from_vision(obs.image_png, "white")
            if hasattr(b, "piece_map") and len(b.piece_map()) >= 2:   # 至少认到两个子才采信
                return b
    except Exception:  # noqa: BLE001
        pass
    return adapter.new_state()


def _play_launch(skill: Skill, world, llm: LLM, role: str | None = None, **_) -> dict:
    """进入对弈 = 把走子循环交给引擎行为树。执方由 role 给（LLM 从对话理解），没给就问——绝不默认选边。
    新框架不再 take_seat/start_game：开局/配对手是世界自己界面上的人类操作（如 sim-chess 网页）。"""
    adapter = get_adapter(skill.adapter_id)
    if adapter is None:
        return {"ok": False, "message": f"没有「{skill.adapter_id}」棋种适配器。"}
    my_side = role if role in ("white", "black") else None
    if my_side is None:
        return {"ok": False, "message": "你想让我执哪一方（白/黑）？告诉我我就开下。"}
    belief = _seed_belief(world, adapter)
    runner = start_boardgame(world, adapter, my_side, narrate=_make_narrator(llm, skill),
                             display_name=skill.display_name, belief=belief)
    side_cn = messages.SIDE_NAMES.get(my_side, my_side)
    reply = messages.game_start_reply(skill.display_name, side_cn[0] if side_cn else "", "对手")
    return {"ok": True, "runner": runner, "display_name": skill.display_name, "reply": reply,
            "my_side": my_side}


def _record_launch(skill: Skill, world, llm: LLM, role: str | None = None, **_) -> dict:
    adapter = get_adapter(skill.adapter_id)
    if adapter is None:
        return {"ok": False, "message": f"没有「{skill.adapter_id}」棋种适配器。"}
    runner = start_record(world, adapter, display_name=skill.display_name)
    return {"ok": True, "runner": runner, "display_name": skill.display_name,
            "reply": "好，我看一眼当前棋盘、记录下来。"}


def _setup_launch(skill: Skill, world, llm: LLM, role: str | None = None, **_) -> dict:
    adapter = get_adapter(skill.adapter_id)
    if adapter is None:
        return {"ok": False, "message": f"没有「{skill.adapter_id}」棋种适配器。"}
    runner = start_setup(world, adapter, display_name=skill.display_name)   # 默认目标 = 标准开局
    return {"ok": True, "runner": runner, "display_name": skill.display_name,
            "reply": "好，我把棋子按标准开局摆到盘上。"}


def _play_chat_reply(message: str, run, llm: LLM) -> str:
    """对弈中闲聊：以对弈伙伴身份回一句。诚实：做不到的别假装能做。
    执方/手数这类任务专属状态只在 skill 侧读，不污染通用主循环。"""
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
    """构造 skill 注册表：一个「下棋家族」= 三个共享 ChessAdapter 的 sub-skill（play/record/setup）。
    以后加五子棋/围棋 = 换适配器、在这里加同一组三行。"""
    reg = SkillRegistry()
    adapter_id = _chess_tools.ChessAdapter.id       # "chess"——skill/适配器 id 单一来源
    game_name = _chess_tools.ChessAdapter.name
    reg.register(Skill(
        id=adapter_id, display_name="Chess Mode · 下棋模式", instructions=PLAY_GAME_INSTRUCTIONS,
        game_name=game_name, required_action="move",     # 对弈需世界能 move
        launcher=_play_launch, adapter_id=adapter_id, chat_reply=_play_chat_reply,
    ))
    reg.register(Skill(
        id=f"{adapter_id}_record", display_name="Record Board · 记录棋盘",
        instructions=RECORD_BOARD_INSTRUCTIONS, game_name=game_name, required_action="move",
        launcher=_record_launch, adapter_id=adapter_id,
    ))
    reg.register(Skill(
        id=f"{adapter_id}_setup", display_name="Setup Board · 摆盘",
        instructions=SETUP_BOARD_INSTRUCTIONS, game_name=game_name, required_action="place",  # 摆盘需世界能 place（物理世界）
        launcher=_setup_launch, adapter_id=adapter_id,
    ))
    return reg
