"""通用 agent loop = **元控制器**（按会话运行）。

设计要点（A1 + 通用运行时）：
- 一个会话绑定一个世界。感知入口 = 这个世界：没连世界 → 纯聊天；连了 → 每轮看它的画面。
- 工具集 = 当前世界的能力（tool）+ 一个 `enter_skill`（当世界上有可进入的 skill 时挂出来，让大脑判断要不要进入）。
- **生命周期归 orchestrator**：进入/退出/暂停/恢复/路由局内意图都在这一层（用 LLM 判断，不写关键词）；
  行为树 runner/manager 是**不做决策的通用运行时**（执行 + 暂停/恢复/求助/落档）。
- 主循环：看 → 想 → 过安全闸 → 动 → 再看，转圈到出最终回复。能力握手一次走缓存；感知每轮真取。
编排器完全通用，对各类世界与技能一视同仁——任务专属细节封装在 skill.launcher / 行为树里，这里一行都不碰。
"""
from __future__ import annotations

import base64

from . import config, context, intent, messages
from .llm import LLM, ToolCall
from .awi import ActionResult, NON_MUTATING_KINDS, ToolSpec
from .registry import WorldRegistry
from .safety import SafetyGate
from .session import Session, SessionStore
from .skill import Skill, SkillRegistry

DEFAULT_MAX_STEPS = config.MAX_STEPS  # ReAct 主循环最多转几轮（config，env 可覆盖）

ENTER_SKILL_TOOL = "enter_skill"      # 大脑用它进入某个 skill（orchestrator 拦截处理，不下发给世界）

# 技能进行中"用户在面板说话"的【通用】意图枚举（结构化分类，不扫词）。
# 注：世界级的过程控制（如暂停/恢复）不在这里——它们是 world 的能力（人按世界页按钮 / ANIMA 自己 invoke），
# 运行时跟着 perceive 到的状态反应，不经 orchestrator。所以这里只留通用的"退出技能 / 闲聊"。
_IN_SKILL_INTENTS = {
    "exit": "想结束/退出这个技能、不玩了",
    "chat": "只是聊两句/问个问题，不要求改变什么",
}


def _tc_dict(tc: ToolCall) -> dict:
    return {"id": tc.id, "name": tc.name, "arguments": tc.arguments}


class Orchestrator:
    def __init__(self, registry: WorldRegistry, store: SessionStore, safety: SafetyGate | None = None,
                 skills: SkillRegistry | None = None, runs=None):
        self.registry = registry
        self.store = store
        self.safety = safety or SafetyGate()
        self.skills = skills            # SkillRegistry | None（脑内技能注册表）
        self.runs = runs               # RunnerManager | None（多棵行为树的通用运行时管理员）
        self._active_skill: dict[str, Skill] = {}   # session.id -> 当前进入的 skill（生命周期归 orchestrator）
        self._persisted: set[int] = set()           # 已落档的技能运行 epoch（幂等：一次运行只折进聊天一次）

    def _world(self, session: Session):
        return self.registry.get(session.world) if session.world else None

    # ==================== skill 生命周期（元控制器职责） ====================
    def active_run(self, session_id: str):
        return self.runs.get(session_id) if self.runs else None

    def _launchable(self, world) -> list[Skill]:
        return self.skills.launchable_on(world) if self.skills else []

    def _enter_skill_tool(self, world) -> list[ToolSpec]:
        """世界上有可进入的 skill 时，给大脑挂一个 enter_skill 工具（枚举可进入的技能 id）。"""
        sk = self._launchable(world)
        if not sk:
            return []
        ids = [s.id for s in sk]
        listing = "；".join(f"{s.id}={s.display_name}" for s in sk)
        return [ToolSpec(
            name=ENTER_SKILL_TOOL,
            description="当你判断用户【现在就想开始/进行】某个技能时，调用它进入该技能的专门模式。"
                        "这些说法都算「想开始」：直接说想做这件事、说「开始吧 / 我们来吧」、让你先动手、"
                        "或说他已经准备好 / 已经配置好了让你接手——只要意图是现在就进行，就调用。"
                        "只是闲聊、问到能力但没要现在做，才不要调。",
            parameters={"type": "object",
                        "properties": {
                            "skill_id": {"type": "string", "enum": ids,
                                         "description": "要进入的技能 id：" + listing},
                            "role": {"type": "string",
                                     "description": "可选：若这个技能需要你先选一个角色/位置才能开始（技能或世界的"
                                                    "工具里会列出可选值），在这里填你要担任的那个角色，进入时会替你选好；"
                                                    "不需要选角色的技能留空。"}},
                        "required": ["skill_id"]},
            kind="read",   # 非世界动作 → 不过安全闸；orchestrator 自己拦截处理
        )]

    def enter(self, session: Session, skill_id: str | None, llm: LLM, role: str | None = None) -> dict:
        """进入一个 skill（启动其行为树）。返回 {ok, reply, display_name?}。enter_skill 工具与 /api/game/start 共用。
        role 是给技能的不透明参数（某些技能需要先选一个角色/位置才能开始）——orchestrator 原样转交，自己不解释它。"""
        world = self._world(session)
        skill = self.skills.get(skill_id) if (self.skills and skill_id) else None
        if skill is None:
            return {"ok": False, "reply": "没有这个技能。"}
        if world is None:
            return {"ok": False, "reply": "这个会话还没连世界，先连一个能玩的世界。"}
        if skill not in self._launchable(world):
            return {"ok": False, "reply": f"当前世界不支持「{skill.display_name}」（没有它需要的能力）。"}
        self.stop_run(session.id)                 # 开新前先停旧（runs.start 也会停，这里同时清 _active_skill）
        res = skill.launcher(skill, world, llm, role=role)   # 配座 + 起行为树（任务专属细节都在 launcher，这里不碰）
        if not res.get("ok"):
            return {"ok": False, "reply": res.get("message", "现在还没法开始。")}
        self.runs.start(session.id, res["runner"])
        self._active_skill[session.id] = skill
        # 开场白由 skill 的 launcher 给（它最懂这个技能怎么开场）；没给就用通用兜底。orchestrator 不拼任何任务专属文案。
        reply = res.get("reply") or messages.skill_entered_reply(res["display_name"])
        return {"ok": True, "reply": reply, "display_name": res["display_name"]}

    def stop_run(self, session_id: str) -> None:
        run = self.active_run(session_id)
        if run is not None and not run.bb.finished:
            # 用户主动停（说"不玩了" / 退出按钮 / 新建会话顶掉旧的）：运行时没机会自己 DoExit 收尾，
            # 这里补一条结束语 + 标记 finished——确保①落档含结束语 ②前端轮询能看到 active=False、面板关闭。
            # （自然结束已由运行时 DoExit 置 finished+结束语，这里 not finished 不会重复。）
            run.bb.emit("end", messages.SKILL_EXIT_REPLY)
            run.bb.finished = True
        self._persist_transcript(session_id)      # 落档（幂等）——在移除 runner 之前，别让记录随树消失
        if self.runs:
            self.runs.stop(session_id)
        self._active_skill.pop(session_id, None)

    def _persist_transcript(self, session_id: str) -> None:
        """把一次技能运行的事件流折进会话历史（主聊天里以技能块呈现）。幂等：按 epoch 去重。"""
        run = self.active_run(session_id)
        if run is None:
            return
        ep = getattr(run.bb, "epoch", 0)
        if ep in self._persisted:
            return
        self._persisted.add(ep)
        block = messages.skill_transcript_block(run.bb.display_name, run.bb.events_since(0))
        if block:
            self.store.append(session_id, {"role": "assistant", "text": block, "skill_transcript": True})

    def finalize_if_done(self, session_id: str) -> None:
        """技能运行已结束（终局/退出）→ 落档一次。供前端轮询时调用。"""
        run = self.active_run(session_id)
        if run is not None and run.finished:
            self._persist_transcript(session_id)

    def route_in_skill(self, session: Session, text: str, llm: LLM) -> dict:
        """技能进行中用户在面板说话：先看是不是在回答 AskHuman；否则分类 退出/闲聊 并作用到 run。
        返回 {ok, reply}。用户的话与 ANIMA 的回应都 emit 成事件（面板事件流可见）。"""
        run = self.active_run(session.id)
        if run is None or run.finished:
            return {"ok": False, "reply": "现在没有进行中的技能。"}
        text = (text or "").strip()
        if not text:
            return {"ok": False, "reply": "空消息"}
        run.bb.emit("user", text)
        # 1) 正在等人回答某个问题（HITL）→ 这句就是答案
        if run.bb.pending_question is not None:
            run.answer(text)
            return {"ok": True, "reply": "（收到，继续。）"}
        # 2) 分类意图（结构化枚举，不扫词；分类失败兜底当闲聊，不静默改变运行状态）
        skill = self._active_skill.get(session.id)
        name = skill.display_name if skill else "当前技能"
        choice = intent.classify(llm, f"用户正在使用「{name}」技能。", text, _IN_SKILL_INTENTS) or "chat"
        if choice == "exit":
            self.stop_run(session.id)                     # 补结束语 + 标记结束 + 落档 + 移除 → 面板会关闭
            return {"ok": True, "reply": messages.SKILL_EXIT_REPLY}
        # 世界级的过程控制（如暂停/恢复）不在这里：那是 world 的能力（人点世界页按钮 / ANIMA 自己 invoke），运行时跟 perceive 状态反应。
        # 闲聊回话交给 skill（它最懂怎么以这个技能的口吻搭话、读自己的任务状态）；没提供则通用兜底。orchestrator 不读任何任务专属状态。
        reply = skill.chat_reply(text, run, llm) if (skill and skill.chat_reply) else messages.SKILL_CHAT_FALLBACK
        run.bb.emit("anima", reply)
        return {"ok": True, "reply": reply}

    # ==================== 主循环 ====================
    def _system(self, world) -> str:
        base = messages.system_prompt()
        if world is None:
            return base + "\n\n当前:未连接任何世界(纯聊天)。"
        s = base + f"\n\n当前已连接世界「{world.name}」,你能在需要时调用它的工具。"
        if self._launchable(world):
            s += messages.SKILL_AVAILABILITY_HINT
        return s

    def _dispatch(self, world, name: str, args: dict) -> ActionResult:
        if world is None:
            return ActionResult(False, "没连接世界,无法操作。")
        return world.invoke(name, **args)

    def _maybe_enter(self, session: Session, reply, llm: LLM) -> str | None:
        """大脑这一拍若调了 enter_skill → 进入该技能、返回确认语（结束本轮）；否则 None。"""
        for tc in reply.tool_calls:
            if tc.name == ENTER_SKILL_TOOL:
                args = tc.arguments or {}
                return self.enter(session, args.get("skill_id"), llm, role=args.get("role"))["reply"]
        return None

    def handle(self, session: Session, user_text: str, llm: LLM, max_steps: int = DEFAULT_MAX_STEPS) -> dict:
        # 技能进行中（兜底：正常情况下前端隐藏聊天框、走 /say）→ 当作面板说话来路由
        run = self.active_run(session.id)
        if run is not None and not run.finished:
            # 不在这里 append 用户消息：route_in_skill 会 emit("user") 进技能事件流，结束时随 transcript 折进聊天，
            # 否则会"聊天历史一条 + transcript 块里一条"双显。
            r = self.route_in_skill(session, user_text, llm)
            return {"reply": r["reply"], "trace": None, "brain": session.brain, "model": llm.model}

        world = self._world(session)
        self.store.append(session.id, {"role": "user", "text": user_text})
        trace: dict = {"inputs": [], "thinking": [], "reply": "", "brain": session.brain, "model": llm.model}

        # ─────────── 主循环:看 → 想 →(过安全闸)→ 动 → 再看 ───────────
        # 不变量(改动时务必保持):capabilities 走缓存、perceive 每轮真取、安全闸只拦「会改世界」的动作、
        #   enter_skill 由 orchestrator 拦截(不下发世界)、handle() 与 handle_stream() 是同一套循环的两个版本(改一个同步另一个)。
        for _ in range(max_steps):
            caps = world.capabilities() if world else None  # 握手:首轮拿能力并缓存
            tools = (list(caps.tools) if caps else []) + self._enter_skill_tool(world)
            kinds = {t.name: t.kind for t in tools}

            obs = world.perceive() if world else None
            image = obs.image_png if obs else None
            if obs:
                self.store.append_perception(session.id, obs.image_png, obs.state)
                trace["inputs"].append({
                    "image_b64": base64.b64encode(obs.image_png).decode() if obs.image_png else None,
                    "state": obs.state,
                })

            history = context.build(self.store.get(session.id).messages)
            reply = llm.chat(self._system(world), history, tools, image)

            if not reply.tool_calls:  # 出文字 → 最终回复,收尾
                self.store.append(session.id, {"role": "assistant", "text": reply.text or "", "brain": session.brain})
                trace["reply"] = reply.text or ""
                return {"reply": reply.text or "", "trace": trace, "brain": session.brain, "model": llm.model}

            entered = self._maybe_enter(session, reply, llm)   # 调了 enter_skill → 进入并收尾
            if entered is not None:
                self.store.append(session.id, {"role": "assistant", "text": entered, "brain": session.brain})
                trace["reply"] = entered
                return {"reply": entered, "trace": trace, "brain": session.brain, "model": llm.model}

            tcs = [_tc_dict(tc) for tc in reply.tool_calls]
            self.store.append(session.id, {"role": "assistant", "text": reply.text or "", "tool_calls": tcs,
                                           "brain": session.brain})
            step = {"text": reply.text or "", "tool_calls": tcs, "tool_results": []}
            trace["thinking"].append(step)

            for tc in reply.tool_calls:  # 执行;下一轮自动重感知(闭环)
                changes_world = world is not None and kinds.get(tc.name, "tool") not in NON_MUTATING_KINDS
                if changes_world:
                    ok, reason = self.safety.check(world, tc.name, tc.arguments)
                    if not ok:
                        result = ActionResult(False, f"安全闸拦截:{reason}")
                        self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                           "content": result.message, "data": result.data})
                        step["tool_results"].append({"name": tc.name, "ok": False, "message": result.message})
                        continue
                result = self._dispatch(world, tc.name, tc.arguments)
                self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                           "content": result.message, "data": result.data})
                step["tool_results"].append({"name": tc.name, "ok": result.ok, "message": result.message})

        trace["reply"] = "（达到最大步数,先停一下。)"
        return {"reply": trace["reply"], "trace": trace, "brain": session.brain, "model": llm.model}

    def handle_stream(self, session: Session, user_text: str, llm: LLM, max_steps: int = DEFAULT_MAX_STEPS):
        """流式版:边跑边 yield 事件。循环逻辑与 handle() 完全一致(改这里务必同步改 handle())。"""
        run = self.active_run(session.id)
        if run is not None and not run.finished:        # 技能进行中 → 路由到面板说话
            # 同 handle()：不在此 append 用户消息（route_in_skill 会 emit 进 transcript），避免双显。
            yield {"type": "start", "brain": session.brain, "model": llm.model}
            r = self.route_in_skill(session, user_text, llm)
            yield {"type": "reply", "text": r["reply"]}
            yield {"type": "done"}
            return

        world = self._world(session)
        self.store.append(session.id, {"role": "user", "text": user_text})
        yield {"type": "start", "brain": session.brain, "model": llm.model}

        for _ in range(max_steps):
            caps = world.capabilities() if world else None
            tools = (list(caps.tools) if caps else []) + self._enter_skill_tool(world)
            kinds = {t.name: t.kind for t in tools}

            obs = world.perceive() if world else None
            if obs:
                self.store.append_perception(session.id, obs.image_png, obs.state)
                yield {
                    "type": "perception",
                    "image_b64": base64.b64encode(obs.image_png).decode() if obs.image_png else None,
                    "state": obs.state,
                }

            history = context.build(self.store.get(session.id).messages)
            reply = llm.chat(self._system(world), history, tools, obs.image_png if obs else None)

            if not reply.tool_calls:  # 出文字 → 最终回复,收尾
                self.store.append(session.id, {"role": "assistant", "text": reply.text or "", "brain": session.brain})
                yield {"type": "reply", "text": reply.text or ""}
                yield {"type": "done"}
                return

            entered = self._maybe_enter(session, reply, llm)   # 调了 enter_skill → 进入并收尾
            if entered is not None:
                self.store.append(session.id, {"role": "assistant", "text": entered, "brain": session.brain})
                yield {"type": "reply", "text": entered}
                yield {"type": "done"}
                return

            tcs = [_tc_dict(tc) for tc in reply.tool_calls]
            self.store.append(session.id, {"role": "assistant", "text": reply.text or "", "tool_calls": tcs,
                                           "brain": session.brain})
            if reply.text:
                yield {"type": "thinking", "text": reply.text}

            for tc in reply.tool_calls:
                yield {"type": "tool_call", "name": tc.name, "args": tc.arguments}
                changes_world = world is not None and kinds.get(tc.name, "tool") not in NON_MUTATING_KINDS
                if changes_world:
                    ok, reason = self.safety.check(world, tc.name, tc.arguments)
                    if not ok:
                        msg = f"安全闸拦截:{reason}"
                        self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name, "content": msg})
                        yield {"type": "tool_result", "name": tc.name, "ok": False, "message": msg}
                        continue
                result = self._dispatch(world, tc.name, tc.arguments)
                self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                           "content": result.message, "data": result.data})
                yield {"type": "tool_result", "name": tc.name, "ok": result.ok, "message": result.message}

        yield {"type": "reply", "text": "（达到最大步数,先停一下。)"}
        yield {"type": "done"}
