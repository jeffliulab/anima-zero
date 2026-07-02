"""通用 agent loop = ANIMA 的 ReAct 主循环（按会话运行）。

v0.6 极简架构：**大脑里只剩两样东西——这个主循环 + 经 MCP 可调的工具**。
- 一个会话绑定一个世界。感知入口 = 这个世界：没连世界 → 纯聊天；连了 → 每轮看它的画面。
- 工具集 = 世界的能力（world 工具）+ 世界声明的挂载服务的能力（service 顾问工具）——
  合并成一张工具单，LLM 自己决定调哪个；分发按来源路由（服务=只读不过闸，世界动作过安全闸）。
- 主循环：看 → 想 → 过安全闸 → 动 → 再看，转圈到出最终回复。能力握手一次走缓存；感知每轮真取。
- 没有任何"模式/技能/任务循环"：多回合的长任务 = 一轮轮普通对话（用户说"该你了/继续"，LLM 自己
  看图认状态、自己调顾问工具算、自己调世界工具动）。HITL = 对话本身（拿不准就直接问用户）。
编排器完全通用，对各类世界与服务一视同仁——任务专属细节住在 world / service 侧，这里一行都不碰。
"""
from __future__ import annotations

import base64
import contextvars
import logging
import queue
import threading

from . import config, context, messages
from .awi import ActionResult, NON_MUTATING_KINDS, ToolSpec
from .llm import LLM, ToolCall
from .registry import WorldRegistry
from .safety import SafetyGate
from .session import Session, SessionStore

DEFAULT_MAX_STEPS = config.MAX_STEPS  # ReAct 主循环最多转几轮（config，env 可覆盖）
_log = logging.getLogger(__name__)


def _tc_dict(tc: ToolCall) -> dict:
    return {"id": tc.id, "name": tc.name, "arguments": tc.arguments}


class Orchestrator:
    def __init__(self, registry: WorldRegistry, store: SessionStore, safety: SafetyGate | None = None):
        self.registry = registry
        self.store = store
        self.safety = safety or SafetyGate()

    def _world(self, session: Session):
        return self.registry.get(session.world) if session.world else None

    # ==================== 工具单组装 ====================
    def _service_toolbox(self, world, world_tool_names: set[str]) -> tuple[list[ToolSpec], dict]:
        """挂载服务的工具单与路由表：tools 并进大脑工具单；routes(name→service) 供分发按来源路由。

        - 服务离线/握手失败 → 它的工具这一轮不上单（等它起来即恢复；诚实呈现，不兜底）。
        - 同名冲突 **world 优先**（约定：service 工具名不得与常见世界动作重名），冲突的服务工具
          不上单并记警告——绝不让一个名字有两个去向。"""
        tools: list[ToolSpec] = []
        routes: dict = {}
        if world is None:
            return tools, routes
        for svc in self.registry.services_for(world):
            try:
                caps = svc.capabilities()
            except Exception:
                continue
            for t in caps.tools:
                if t.name in world_tool_names:
                    _log.warning("服务工具与世界工具同名，按约定世界优先：%s（来自 %s）", t.name, svc.name)
                    continue
                routes[t.name] = svc
                tools.append(t)
        return tools, routes

    # ==================== 系统提示 ====================
    def _system(self, world, has_services: bool = False) -> str:
        base = messages.system_prompt()
        if world is None:
            return base + "\n\n当前:未连接任何世界(纯聊天)。"
        # 这个世界能不能操作,由它的【能力声明】决定(通用,不针对具体世界):
        #   有工具 → 可在需要时调用;空工具(如 camera 摄像头世界)→ 只能看 + 聊,无任何动作可调。
        # capabilities() 在 RemoteWorld 侧已缓存,这里再读一次不发 HTTP。
        try:
            caps = world.capabilities()
            has_tools = bool(caps.tools)
            guidance = caps.guidance
        except Exception:
            has_tools, guidance = True, ""   # 读不到能力时不臆断"不可操作",保持旧行为(由后续真正调用兜底)
        if has_tools:
            s = base + f"\n\n当前已连接世界「{world.name}」,你能在需要时调用它的工具。"
        else:
            s = base + f"\n\n当前已连接世界「{world.name}」,它没有提供任何可调动作——你只能看画面、和用户聊,无法操作它。"
        # 世界的「说明书」(guidance = MCP prompt)：世界自我介绍怎么跟它打交道。让大脑保持纯净通用——
        # 不为某个世界写死逻辑，改由世界自述、大脑读了就懂。
        if guidance:
            s += f"\n\n【这个世界的说明书（它自己写的，教你怎么跟它打交道）】\n{guidance}"
        if has_services:
            s += messages.SERVICES_HINT
        return s

    # ==================== 分发 ====================
    def _dispatch(self, world, name: str, args: dict, _on_progress=None) -> ActionResult:
        if world is None:
            return ActionResult(False, "没连接世界,无法操作。")
        if _on_progress is not None:
            return world.invoke(name, _on_progress=_on_progress, **args)
        return world.invoke(name, **args)

    # ==================== 主循环 ====================
    def handle(self, session: Session, user_text: str, llm: LLM, max_steps: int = DEFAULT_MAX_STEPS) -> dict:
        world = self._world(session)
        self.store.append(session.id, {"role": "user", "text": user_text})
        trace: dict = {"inputs": [], "thinking": [], "reply": "", "brain": session.brain, "model": llm.model}

        # ─────────── 主循环:看 → 想 →(过安全闸)→ 动 → 再看 ───────────
        # 不变量(改动时务必保持):capabilities 走缓存、perceive 每轮真取、安全闸只拦「会改世界」的动作、
        #   服务工具按来源路由(只读不过闸)、handle() 与 handle_stream() 是同一套循环的两个版本(改一个同步另一个)。
        for _ in range(max_steps):
            caps = world.capabilities() if world else None  # 握手:首轮拿能力并缓存
            world_tools = list(caps.tools) if caps else []
            svc_tools, svc_routes = self._service_toolbox(world, {t.name for t in world_tools})
            tools = world_tools + svc_tools
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
            reply = llm.chat(self._system(world, has_services=bool(svc_tools)), history, tools, image)

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
                result = self._run_tool(world, svc_routes, kinds, tc)
                self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                   "content": result.message, "data": result.data})
                step["tool_results"].append({"name": tc.name, "ok": result.ok, "message": result.message})

        trace["reply"] = messages.MAX_STEPS_REPLY
        return {"reply": trace["reply"], "trace": trace, "brain": session.brain, "model": llm.model}

    def _run_tool(self, world, svc_routes: dict, kinds: dict, tc: ToolCall, _on_progress=None) -> ActionResult:
        """执行一个工具调用：服务工具（顾问=只读）路由给服务、不过安全闸；世界动作先过闸再发。"""
        svc = svc_routes.get(tc.name)
        if svc is not None:
            return svc.invoke(tc.name, **tc.arguments)
        changes_world = world is not None and kinds.get(tc.name, "tool") not in NON_MUTATING_KINDS
        if changes_world:
            ok, reason = self.safety.check(world, tc.name, tc.arguments)
            if not ok:
                return ActionResult(False, f"安全闸拦截:{reason}")
        return self._dispatch(world, tc.name, tc.arguments, _on_progress=_on_progress)

    def handle_stream(self, session: Session, user_text: str, llm: LLM, max_steps: int = DEFAULT_MAX_STEPS):
        """流式版:边跑边 yield 事件。循环逻辑与 handle() 完全一致(改这里务必同步改 handle())。

        长动作进度：世界工具在后台线程里执行，其 MCP progress 经队列转成 "progress" 事件实时下发
        （用户看到"已夹取，正在移向 e4"而不是黑等几十秒）。"""
        world = self._world(session)
        self.store.append(session.id, {"role": "user", "text": user_text})
        yield {"type": "start", "brain": session.brain, "model": llm.model}

        for _ in range(max_steps):
            caps = world.capabilities() if world else None
            world_tools = list(caps.tools) if caps else []
            svc_tools, svc_routes = self._service_toolbox(world, {t.name for t in world_tools})
            tools = world_tools + svc_tools
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
            reply = llm.chat(self._system(world, has_services=bool(svc_tools)), history, tools,
                             obs.image_png if obs else None)

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
                yield from self._run_tool_streaming(session, world, svc_routes, kinds, tc)

        yield {"type": "reply", "text": messages.MAX_STEPS_REPLY}
        yield {"type": "done"}

    def _run_tool_streaming(self, session: Session, world, svc_routes: dict, kinds: dict, tc: ToolCall):
        """流式执行一个工具调用：进度事件实时 yield，最后 yield tool_result（结果同时落会话历史）。

        世界动作可能几十秒：invoke 放后台线程跑（contextvars 复制保 session 标签），
        MCP progress 回调进队列 → 这里实时转成 "progress" 事件；服务/被拦截的调用即时返回，无进度。"""
        svc = svc_routes.get(tc.name)
        changes_world = svc is None and world is not None and kinds.get(tc.name, "tool") not in NON_MUTATING_KINDS
        if changes_world:
            ok, reason = self.safety.check(world, tc.name, tc.arguments)
            if not ok:
                msg = f"安全闸拦截:{reason}"
                self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name, "content": msg})
                yield {"type": "tool_result", "name": tc.name, "ok": False, "message": msg}
                return

        q: queue.Queue = queue.Queue()
        holder: dict = {}

        def _on_progress(message, progress, total):
            q.put({"type": "progress", "name": tc.name, "message": message or "", "progress": progress})

        def _work():
            if svc is not None:
                holder["res"] = svc.invoke(tc.name, **tc.arguments)
            else:
                holder["res"] = self._dispatch(world, tc.name, tc.arguments, _on_progress=_on_progress)

        ctx = contextvars.copy_context()             # 后台线程继承 session 标签（session_log 记账不丢归属）
        th = threading.Thread(target=ctx.run, args=(_work,), daemon=True)
        th.start()
        while th.is_alive():
            try:
                yield q.get(timeout=config.BRIDGE_WATCHDOG_POLL_S)
            except queue.Empty:
                pass
        th.join()
        while not q.empty():                          # 清掉收尾前最后一批进度
            yield q.get()
        result: ActionResult = holder.get("res") or ActionResult(False, "（工具执行线程异常退出）")
        self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                       "content": result.message, "data": result.data})
        yield {"type": "tool_result", "name": tc.name, "ok": result.ok, "message": result.message}
