"""文案 / 提示词集中处（脑侧）—— 禁止在代码里内联写死字符串。

包括：编排器 SYSTEM 提示词（可 env 覆盖、便于 A/B）、对弈解说/回复模板、侧名映射等。
（域字面量如 "white"/"black" 仍在协议层；这里放"给人看的文案"。）
"""
from __future__ import annotations

import os

# ---- 编排器系统提示词（可用 ANIMA_SYSTEM_PROMPT 覆盖；trace 里可记版本）----
_SYSTEM_DEFAULT = (
    "你是 ANIMA,一个具身机器人的「大脑」。你通过调用「世界」提供的工具来观察和操作它。\n"
    "\n"
    "【关于工具——最重要】\n"
    "工具是你在“需要时”才使用的能力,不是一份“必须执行的清单”。看到有工具可用、或看到世界的画面,"
    "都不等于要你动手。\n"
    "\n"
    "【每一轮:先判断,再决定】\n"
    "每收到用户一条消息,先在心里判断一句:用户这一轮是不是在明确要求一个物理动作(移动、书写、画线、放置……)?\n"
    "· 是 → 只调用完成它所需的那一个工具;做完后若世界提供了裁判工具(judge),调它确认成没成。\n"
    "· 否(打招呼、寒暄、提问、让你描述看到了什么、闲聊)→ 只用文字回应,绝不调用任何工具。\n"
    "\n"
    "【纪律】\n"
    "· 你自己从不直接动手,只能通过调用工具操作世界;但“能调”不等于“该调”。\n"
    "· 一个请求只调它真正需要的那一个工具,够了就停;不重复调、不顺手多做用户没要求的事。\n"
    "· 拿不准用户到底要不要动手时,先用文字问清楚,而不是直接动手。\n"
    "· 没连接任何世界时,你就是个纯聊天助手。"
)


def system_prompt() -> str:
    return os.getenv("ANIMA_SYSTEM_PROMPT", _SYSTEM_DEFAULT)


# 当大脑有可进入的 skill 时，追加这段（告诉它"想做这类任务就调 enter_skill"）。游戏无关。
SKILL_AVAILABILITY_HINT = (
    "\n\n【你还会一些「技能(skill)」】下面的工具里有一类是 `enter_skill`：当你判断用户**想开始做某个技能"
    "对应的任务**（比如想下棋）时，就调用对应的 enter_skill 进入该技能；不确定就先用文字问清楚。不要凭"
    "关键词机械判断，按整句意思理解。"
)

# ---- 对弈相关文案 ----
SIDE_NAMES = {"white": "白方", "black": "黑方", "draw": "和棋"}
OPPONENT_NAMES = {"bot": "电脑", "human": "你自己"}   # 对手那一方由谁下


def narrate_template(san: str, uci: str) -> str:
    """headless / LLM 不可用时的兜底解说。"""
    return f"我走 {san}（{uci}）。"


def game_start_reply(display_name: str, my_side_cn: str, opponent: str, defaulted: bool = False) -> str:
    """进入对弈的确认语（enter_skill / 认领席位成功后）。opponent 由世界返回的 controllers 决定。"""
    opp = OPPONENT_NAMES.get(opponent, opponent)
    return f"好，进入 {display_name} ♟ 我执{my_side_cn}、对手是{opp}，棋盘在面板里实时更新。"


# ---- 通用技能生命周期文案（orchestrator 用，任何技能通用、不带任务专属词）----
SKILL_EXIT_REPLY = "好，那就不玩了，退出当前技能。"        # 退出某个技能时的兜底结束语（编排器与各技能行为树共用）
SKILL_CHAT_FALLBACK = "嗯，我在。"                          # 技能进行中用户闲聊、而该技能没提供专属搭话时的兜底
HITL_TIMEOUT_REPLY = "等待人类回答超时——安全起见我先停下这次运行（真机上不能让一个没人回的问题无限挂着）。"  # AskHuman 超时的安全中止


def skill_entered_reply(display_name: str) -> str:
    """通用进入确认语（当 skill.launcher 没给定制开场白时的兜底；编排器不拼任务专属文案）。"""
    return f"好，进入「{display_name}」。"


# ---- 对弈相关文案（续）----
GAME_SEAT_LOST_REPLY = "我这一方被换人接管了，那我先退出这盘。"   # 对局中世界把我的席位换给了别人（human/bot）→ 如实退出
GAME_PAUSE_REPLY = "好，先暂停，棋盘停在当前这步；你说「继续」我就接着下。"
GAME_RESUME_REPLY = "好，继续，从当前局面接着下。"
GAME_RESIGN_REPLY = "这局我落后太多、基本没希望了，我认输，退出这盘。"  # 引擎评分判定的主动认输
GAME_OVER_REPLY = "这盘下完了（世界判了终局），我退出对弈。"                 # 世界 phase=game_over → 收尾


# ---- 技能运行结束后：把事件流折进主聊天的分隔块（通用，任何技能都用这一个）----
_TRANSCRIPT_WHO = {"anima": "ANIMA", "user": "你", "opponent": "对手", "end": "", "start": ""}


def skill_transcript_block(display_name: str, events: list[dict]) -> str:
    """把一次技能运行的事件流（动作+解说+结束语）拼成一段 markdown，供退出后展示在主聊天里。
    空运行返回空串（不落一个空块）。"""
    if not events:
        return ""
    lines = []
    for e in events:
        who = _TRANSCRIPT_WHO.get(e.get("channel", ""), "")
        prefix = f"{who}：" if who else ""
        lines.append(f"`[{e.get('ts', '')}]` {prefix}{e.get('text', '')}")
    body = "  \n".join(lines)   # markdown 行内换行（句末两空格）
    return f"**——— {display_name} · 技能开始 ———**\n\n{body}\n\n**——— {display_name} · 技能结束 ———**"


def game_end_text(reason: str, winner: str, i_won: bool) -> str:
    if winner == "draw":
        return f"棋局结束（{reason}）：和棋。"
    who = SIDE_NAMES.get(winner, "")
    return f"棋局结束（{reason}）：{who}胜，我{'赢了！' if i_won else '输了。'}"
