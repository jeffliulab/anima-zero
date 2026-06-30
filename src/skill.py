"""skill —— ANIMA 的"使用说明书 + 怎么进入"（程序性知识包）+ 轻量注册表。

⛔ skill ≠ tool。tool=世界声明的原子能力（AWI 上跨线的那个东西）；skill=一份**脑内剧本**（教大脑碰到一类
任务怎么把它干好，像 Agent Skills 的 SKILL.md）。skill 不上 AWI 线、世界不知道它存在。

一个 skill 含：给用户看的 `display_name`、注入解说/陪聊的 `instructions`、这类玩法的 `game_name`（中文名，
供提示词参数化用、不再把"国际象棋"写死）、进入所需的世界能力 `required_action`（靠能力查询判断可否进入）、
以及 `launcher`（把"怎么在某个世界上起这局"封装起来——配座/起行为树都在里面，orchestrator 只管调它）。
"维持对弈循环"不在 skill 里——那是更高一层的**对弈行为树**（runner 跑）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class Skill:
    id: str                 # 内部 id，如 "chess"
    display_name: str       # 给用户看的名字，如 "Chess Mode · 下棋模式"
    instructions: str       # 注入系统提示的说明书正文（解说/陪聊用）
    game_name: str          # 这类玩法的中文名（如 "国际象棋"）——供提示词参数化，不再写死
    required_action: str    # 进入所需的世界能力名（如 "move"）——靠能力查询判断可否进入（不靠世界名）
    launcher: Callable[..., dict]   # (skill, world, llm, role=None) -> {"ok","runner","display_name","reply"?,...}
    #   role=进入时大脑想担任的角色/位置（不透明字符串，某些技能需要先选角色才能开始）；"reply"=可选的定制开场白
    adapter_id: str         # 棋种适配器 id（单一来源，通常 == skill.id）
    # 可选：技能进行中用户闲聊时的搭话回调 (message, run, llm)->一句话。任务专属状态（如执方/手数）只该在这里读，
    # 不上浮到通用 orchestrator；没给则编排器用通用兜底（messages.SKILL_CHAT_FALLBACK）。
    chat_reply: Optional[Callable[..., str]] = None
    # ⛔ 不放关键词触发列表：进入/退出/暂停意图由 LLM 判断（见 orchestrator + intent.classify），不写死关键词。


class SkillRegistry:
    """进程内 dict，轻量（skill 是脑内纯逻辑，不需要远程 World 那套握手/探活）。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def launchable_on(self, world: Any) -> list[Skill]:
        """这个世界上**能进入**哪些 skill：靠能力查询——世界声明了该 skill 的 required_action 才算。"""
        if world is None:
            return []
        try:
            names = {t.name for t in world.capabilities().tools}
        except Exception:
            return []
        return [s for s in self._skills.values() if s.required_action in names]
