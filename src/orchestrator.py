"""通用 agent loop(按会话运行)。

设计要点(5.1:主循环极简,功夫在外围):
- 一个会话绑定一个世界(session.world)。感知入口 = 这个世界:没连世界 → 纯聊天;连了 → 每轮看它的画面。
- 工具集 = 当前世界的能力(裁判以后也是世界提供的一个工具,见 §5.1)。
- 主循环:看 → 想 → 过安全闸 → 动 → 再看,转圈到出最终回复(每轮的固定顺序见 handle() 里的结构注释)。
  能力(工具清单)握手一次后走缓存;感知(画面+状态)每轮真取一次。
- 记忆按会话存在本地(SessionStore);每轮产出一份结构化轨迹(给前端两层折叠 + 当 episode 记录)。
编排器完全通用,对桌面 / 棋 / 人形一视同仁。
"""
from __future__ import annotations

import base64

from . import context
from .llm import LLM, ToolCall
from .awi import ActionResult, NON_MUTATING_KINDS
from .registry import WorldRegistry
from .safety import SafetyGate
from .session import Session, SessionStore

DEFAULT_MAX_STEPS = 8  # ReAct / TAO 主循环最多转几轮(看→想→动→再看)

SYSTEM = (
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


def _tc_dict(tc: ToolCall) -> dict:
    return {"id": tc.id, "name": tc.name, "arguments": tc.arguments}


class Orchestrator:
    def __init__(self, registry: WorldRegistry, store: SessionStore, safety: SafetyGate | None = None):
        self.registry = registry
        self.store = store
        self.safety = safety or SafetyGate()

    def _world(self, session: Session):
        return self.registry.get(session.world) if session.world else None

    def _system(self, world) -> str:
        if world is None:
            return SYSTEM + "\n\n当前:未连接任何世界(纯聊天)。"
        return SYSTEM + f"\n\n当前已连接世界「{world.name}」,你能在需要时调用它的工具。"

    def _dispatch(self, world, name: str, args: dict) -> ActionResult:
        if world is None:
            return ActionResult(False, "没连接世界,无法操作。")
        return world.invoke(name, **args)

    def handle(self, session: Session, user_text: str, llm: LLM, max_steps: int = DEFAULT_MAX_STEPS) -> dict:
        world = self._world(session)
        self.store.append(session.id, {"role": "user", "text": user_text})
        trace: dict = {"inputs": [], "thinking": [], "reply": "", "brain": session.brain, "model": llm.model}

        # ─────────── 主循环:看 → 想 →(过安全闸)→ 动 → 再看 ───────────
        # 一条用户消息进来,转圈到「大脑只出文字」为止。每一轮固定这个顺序,别打乱:
        #   1) 看·能力  capabilities(): 取工具清单 + 各自 kind。已握手缓存,之后不再问世界。
        #   2) 看·画面  perceive():     每轮都真取一帧(状态+图)。这是具身闭环的根,别改成「懒加载/按需才看」。
        #   3) 想       llm.chat():      把 [系统说明+历史+工具+画面] 交给大脑,它决定「只回话」还是「调工具」。
        #   4) 只回话 → 这段文字就是最终回复,收尾 return。
        #   5) 调了工具 → 逐个:会改世界的先过安全闸(不经过 LLM),再 invoke;然后回到第 1 步重看(闭环纠错)。
        #   兜底:转满 max_steps 仍没收尾 → 回一句话收尾,防死循环。
        # 不变量(改动时务必保持):capabilities 走缓存、perceive 每轮真取、安全闸只拦「会改世界」的动作、
        #   handle() 与 handle_stream() 是同一套循环的「整段版 / 流式版」,改一个必须同步改另一个。
        for _ in range(max_steps):
            caps = world.capabilities() if world else None  # 握手:首轮拿能力并缓存,之后命中缓存不再问世界
            tools = list(caps.tools) if caps else []
            kinds = {t.name: t.kind for t in tools}

            obs = world.perceive() if world else None
            image = obs.image_png if obs else None
            if obs:
                self.store.append_perception(session.id, obs.image_png, obs.state)
                trace["inputs"].append({
                    "image_b64": base64.b64encode(obs.image_png).decode() if obs.image_png else None,
                    "state": obs.state,
                })

            history = context.build(self.store.get(session.id).messages)  # 滑窗 + 丢图(5.1:上下文稀缺)
            reply = llm.chat(self._system(world), history, tools, image)

            if not reply.tool_calls:  # 出文字 → 最终回复,收尾
                self.store.append(session.id, {"role": "assistant", "text": reply.text or "", "brain": session.brain})
                trace["reply"] = reply.text or ""
                return {"reply": reply.text or "", "trace": trace, "brain": session.brain, "model": llm.model}

            tcs = [_tc_dict(tc) for tc in reply.tool_calls]
            self.store.append(session.id, {"role": "assistant", "text": reply.text or "", "tool_calls": tcs,
                                           "brain": session.brain})
            step = {"text": reply.text or "", "tool_calls": tcs, "tool_results": []}
            trace["thinking"].append(step)

            for tc in reply.tool_calls:  # 执行;下一轮自动重感知(闭环)
                # 只有「会改世界」的动作过安全闸(裁判 / 只读工具不算改世界)
                changes_world = world is not None and kinds.get(tc.name, "tool") not in NON_MUTATING_KINDS
                if changes_world:
                    ok, reason = self.safety.check(world, tc.name, tc.arguments)  # 不经过 LLM 的确定性闸
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
        """流式版:边跑边 yield 事件(给前端像 ChatGPT 一样滚动展示过程)。记录照常落盘。"""
        world = self._world(session)
        self.store.append(session.id, {"role": "user", "text": user_text})
        yield {"type": "start", "brain": session.brain, "model": llm.model}

        # 流式版:循环逻辑与 handle() 完全一致(结构 + 不变量见 handle() 上方的注释);改这里务必同步改 handle()。
        for _ in range(max_steps):
            caps = world.capabilities() if world else None  # 握手:首轮拿能力并缓存,之后命中缓存
            tools = list(caps.tools) if caps else []
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
