"""通用 agent loop = ANIMA 的 ReAct 主循环（按会话运行）——LangGraph StateGraph 骨架。

v0.5 重构后的极简架构：**大脑里只剩两样东西——这个主循环 + 经 MCP 可调的工具**。
- 一个会话绑定一个世界。感知入口 = 这个世界：没连世界 → 纯聊天；连了 → 每轮看它的画面。
- 工具集 = 世界的能力（world 工具）+ 世界声明的挂载服务的能力（service 顾问工具）——
  合并成一张工具单，LLM 自己决定调哪个；分发按来源路由（服务=只读不过闸，世界动作过安全闸）。
- 没有任何"模式/技能/任务循环"：多回合的长任务 = 一轮轮普通对话（用户说"该你了/继续"，LLM 自己
  看图认状态、自己调顾问工具算、自己调世界工具动）。HITL = 对话本身（拿不准就直接问用户）。

【LangGraph 集成方式：骨架用它、内脏用自己的】
图结构（一次编译，节点=普通方法，内部全是自有模块——LLM 协议层/MCP 桥不换 LangChain 抽象）：
    START → perceive → agent ─(出文字)→ END
                         └─(要调工具)→ act ─(闸门都没到)→ perceive（回环）
                                          └─(撞到闸门)→ overflow → END
- 每条用户消息 = 一次图运行（种子从 SessionStore 读，会话真相始终在 SessionStore）；
  **不启用跨轮 checkpointer**——LangGraph 的持久化/中断/认知子图留给将来（先别做）。
- 流式：节点经 get_stream_writer() 发自定义事件（perception/thinking/tool_call/progress/
  tool_result/reply），handle_stream 用 stream_mode="custom" 原样转发——SSE 事件形状不变，
  前端零改动；非流式 invoke 下 writer 是安全的 no-op（已验证），handle 与 handle_stream 共用同一张图。
- 一轮**什么时候收尾由 LLM 自己决定**（它一出文字就结束）；三个闸只在它转不出来时兜底，
  经 act 后的条件边判断（不靠 recursion_limit 报错；limit 只按图深度放宽为安全带）：
  步数上限 config.MAX_STEPS / 墙钟上限 config.TURN_TIME_BUDGET_S / 用户在网页点了停止。
  三者都走 overflow 节点=**可续的停顿**（核心任务留在册，用户说「继续」接着来），不是报错。
编排器完全通用，对各类世界与服务一视同仁——任务专属细节住在 world / service 侧，这里一行都不碰。
"""
from __future__ import annotations

import base64
import contextvars
import logging
import queue
import threading
import time
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .. import config, messages
from ..session import context
from . import interrupt
from .awi import ActionResult, NON_MUTATING_KINDS, ToolSpec
from ..llm import LLM, LLMReply, ToolCall
from ..clients.registry import WorldRegistry
from .safety import SafetyGate
from ..session import Session, SessionStore

DEFAULT_MAX_STEPS = config.MAX_STEPS                     # 单轮步数上限（config，env 可覆盖）
DEFAULT_TURN_TIME_BUDGET_S = config.TURN_TIME_BUDGET_S   # 单轮墙钟上限（同上）
_NODES_PER_STEP = 3                   # 每轮回环经过的节点数（perceive→agent→act），算 recursion_limit 安全带用
_log = logging.getLogger(__name__)


def _tc_dict(tc: ToolCall) -> dict:
    return {"id": tc.id, "name": tc.name, "arguments": tc.arguments}


class LoopState(TypedDict, total=False):
    """一次图运行的状态（不序列化、不跨轮持久——会话真相在 SessionStore）。"""
    session: Session
    llm: Any                 # LLM 协议对象（自有层，非 LangChain 模型）
    max_steps: int
    deadline: float          # 本轮墙钟死线（time.monotonic() 基准；到点即收尾）
    step: int                # 已开始第几轮（perceive 时 +1）
    world: Any               # RemoteWorld | None
    svc_routes: dict         # 工具名 → service 客户端（本轮）
    kinds: dict              # 工具名 → kind（本轮）
    tools: list              # 本轮工具单
    meta_names: set          # 本轮内建元工具名（核心任务两件；分发时优先拦截）
    image: Any               # 本轮画面（bytes | None）
    reply: Any               # 本轮 LLMReply
    trace: dict              # handle() 返回的调试轨迹（inputs/thinking/reply）
    final_reply: str
    done: bool


class Orchestrator:
    def __init__(self, registry: WorldRegistry, store: SessionStore, safety: SafetyGate | None = None):
        self.registry = registry
        self.store = store
        self.safety = safety or SafetyGate()
        self._graph = self._build_graph()

    def _world(self, session: Session):
        return self.registry.get(session.world) if session.world else None

    # ==================== 图组装 ====================
    def _build_graph(self):
        g = StateGraph(LoopState)
        g.add_node("perceive", self._node_perceive)
        g.add_node("agent", self._node_agent)
        g.add_node("act", self._node_act)
        g.add_node("overflow", self._node_overflow)
        g.add_edge(START, "perceive")
        g.add_edge("perceive", "agent")
        g.add_conditional_edges("agent", lambda s: END if s.get("done") else "act",
                                {END: END, "act": "act"})
        g.add_conditional_edges("act",
                                lambda s: "overflow" if self._stop_reason(s) else "perceive",
                                {"overflow": "overflow", "perceive": "perceive"})
        g.add_edge("overflow", END)
        return g.compile()

    def _stop_reason(self, state: LoopState) -> str | None:
        """这一轮该不该在这里收尾？三个闸谁先到算谁；None = 接着转。

        顺序有意：**用户叫停排第一**——他按了停就该停，不该因为"步数还没到"再多走一步。
        """
        if interrupt.is_set(state["session"].id):
            return "interrupt"
        if state["step"] >= state["max_steps"]:
            return "steps"
        if time.monotonic() >= state["deadline"]:
            return "time"
        return None

    # ==================== 节点（看 → 想 → 动）====================
    # 不变量(改动时务必保持):capabilities 走缓存、perceive 每轮真取、安全闸只拦「会改世界」的动作、
    #   服务工具按来源路由(只读不过闸)、handle 与 handle_stream 共用同一张图(行为天然一致)。

    def _node_perceive(self, state: LoopState) -> dict:
        """看：拿本轮工具单（世界+服务+内建元工具）与画面；画面落会话历史并发 perception 事件。"""
        emit = get_stream_writer()
        session, world = state["session"], state["world"]
        caps = world.capabilities() if world else None      # 握手:首轮拿能力并缓存
        world_tools = list(caps.tools) if caps else []
        svc_tools, svc_routes = self._service_toolbox(world, {t.name for t in world_tools})
        meta_tools = self._meta_toolbox({t.name for t in world_tools} | set(svc_routes))
        tools = world_tools + svc_tools + meta_tools

        obs = world.perceive() if world else None
        # 多相机：把全套命名图交给 LLM（provider 会给每张标相机名）；单相机/无名图=老形状 bytes，行为不变。
        image = None
        if obs:
            image = obs.images if len(obs.images) > 1 else obs.image_png
            self.store.append_perception(session.id, obs.image_png, obs.state, images=obs.images)
            img_b64 = base64.b64encode(obs.image_png).decode() if obs.image_png else None
            state["trace"]["inputs"].append({"image_b64": img_b64, "state": obs.state,
                                             "n_images": len(obs.images)})
            emit({"type": "perception", "image_b64": img_b64, "state": obs.state,
                  "n_images": len(obs.images)})
        return {"step": state.get("step", 0) + 1, "tools": tools, "svc_routes": svc_routes,
                "kinds": {t.name: t.kind for t in tools}, "image": image, "trace": state["trace"],
                "meta_names": {t.name for t in meta_tools}}

    def _node_agent(self, state: LoopState) -> dict:
        """想：拼系统提示+历史+工具单 → 自有 LLM 层 chat()（LoggingLLM 记账不动）。"""
        emit = get_stream_writer()
        session, llm, world = state["session"], state["llm"], state["world"]
        svc_tools_present = bool(state["svc_routes"])
        stored = self.store.get(session.id)      # 每步现读：历史 + 核心任务寄存器（本轮内改写立即生效）
        history = context.build(stored.messages)
        reply: LLMReply = llm.chat(self._system(world, has_services=svc_tools_present,
                                                core_task=stored.core_task),
                                   history, state["tools"], state["image"])

        if not reply.tool_calls:    # 出文字 → 最终回复,收尾
            self.store.append(session.id, {"role": "assistant", "text": reply.text or "",
                                           "brain": session.brain})
            state["trace"]["reply"] = reply.text or ""
            emit({"type": "reply", "text": reply.text or ""})
            return {"reply": reply, "done": True, "final_reply": reply.text or "", "trace": state["trace"]}

        tcs = [_tc_dict(tc) for tc in reply.tool_calls]
        self.store.append(session.id, {"role": "assistant", "text": reply.text or "", "tool_calls": tcs,
                                       "brain": session.brain})
        state["trace"]["thinking"].append({"text": reply.text or "", "tool_calls": tcs, "tool_results": []})
        if reply.text:
            emit({"type": "thinking", "text": reply.text})
        return {"reply": reply, "done": False, "trace": state["trace"]}

    def _node_act(self, state: LoopState) -> dict:
        """动：逐个执行本轮工具调用（服务→路由给顾问；世界→过安全闸），结果落历史+事件；下轮自动重感知（闭环）。"""
        emit = get_stream_writer()
        session, world = state["session"], state["world"]
        step_trace = state["trace"]["thinking"][-1]
        for tc in state["reply"].tool_calls:
            emit({"type": "tool_call", "name": tc.name, "args": tc.arguments})
            result = self._run_tool(session, world, state["svc_routes"], state["kinds"], tc, emit,
                                    meta_names=state.get("meta_names") or set())
            step_trace["tool_results"].append({"name": tc.name, "ok": result.ok, "message": result.message})
        return {"trace": state["trace"]}

    def _node_overflow(self, state: LoopState) -> dict:
        """撞到闸门（步数/墙钟/用户叫停）：按原因说一句人话收尾，用户再说一句即可继续。

        收尾语**要落进会话历史**：网页在流结束后用会话记录重绘这一轮，不落库的话这句话会
        在重绘时凭空消失，看起来像"跑着跑着没了"。
        """
        emit = get_stream_writer()
        session = state["session"]
        reason = self._stop_reason(state) or "steps"
        interrupt.clear(session.id)     # 这次叫停已被消费，别殃及用户接着说的下一句
        text = messages.STOP_REPLIES[reason]
        self.store.append(session.id, {"role": "assistant", "text": text, "brain": session.brain})
        state["trace"]["reply"] = text
        emit({"type": "reply", "text": text, "stop_reason": reason})
        return {"final_reply": text, "done": True, "trace": state["trace"]}

    # ==================== 工具执行 ====================
    def _run_tool(self, session: Session, world, svc_routes: dict, kinds: dict,
                  tc: ToolCall, emit, meta_names: set | None = None) -> ActionResult:
        """执行一个工具调用：内建元工具（操作大脑自己的会话状态）直接处理；服务工具（顾问=只读）
        路由给服务、不过安全闸；世界动作先过闸再发。
        世界动作可能几十秒：放后台线程跑（contextvars 复制保 session 标签），MCP progress 经
        队列转成 "progress" 事件实时发出（用户看到"已夹取，正在移向 e4"，不黑等）。
        结果统一落会话历史（role=tool）+ 发 tool_result 事件。"""
        if meta_names and tc.name in meta_names:   # 元工具不碰世界：不过安全闸、不进路由
            return self._run_meta_tool(session, tc, emit)
        svc = svc_routes.get(tc.name)
        changes_world = svc is None and world is not None and kinds.get(tc.name, "tool") not in NON_MUTATING_KINDS
        if changes_world:
            ok, reason = self.safety.check(world, tc.name, tc.arguments)
            if not ok:
                result = ActionResult(False, f"安全闸拦截:{reason}")
                self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                               "content": result.message})
                emit({"type": "tool_result", "name": tc.name, "ok": False, "message": result.message})
                return result

        q: queue.Queue = queue.Queue()
        holder: dict = {}

        def _on_progress(message, progress, total):
            q.put({"type": "progress", "name": tc.name, "message": message or "", "progress": progress})

        # 世界动作可能几十秒（机器狗走一步就要好几秒）——等待期间也要能被用户叫停，
        # 否则点了停止还得干等这一步走完。世界客户端本来就支持（0.25s 粒度巡检），接上即可。
        def _aborted() -> bool:
            return interrupt.is_set(session.id)

        def _work():
            if svc is not None:
                holder["res"] = svc.invoke(tc.name, **tc.arguments)
            else:
                holder["res"] = self._dispatch(world, tc.name, tc.arguments,
                                               _on_progress=_on_progress, _should_abort=_aborted)

        ctx = contextvars.copy_context()             # 后台线程继承 session 标签（session_log 记账不丢归属）
        th = threading.Thread(target=ctx.run, args=(_work,), daemon=True)
        th.start()
        while th.is_alive():
            try:
                emit(q.get(timeout=config.BRIDGE_WATCHDOG_POLL_S))
            except queue.Empty:
                pass
        th.join()
        while not q.empty():                          # 清掉收尾前最后一批进度
            emit(q.get())
        result: ActionResult = holder.get("res") or ActionResult(False, "（工具执行线程异常退出）")
        self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                       "content": result.message, "data": result.data})
        emit({"type": "tool_result", "name": tc.name, "ok": result.ok, "message": result.message})
        return result

    def _run_meta_tool(self, session: Session, tc: ToolCall, emit) -> ActionResult:
        """内建元工具：操作大脑自己的会话状态（核心任务寄存器）。通用机制——「当前在执行什么任务」
        是状态不是聊天记录，由 LLM 亲自登记/改写/清除，常驻注入系统提示（见 _system）。"""
        if tc.name == messages.CORE_TASK_SET_TOOL["name"]:
            task = str(tc.arguments.get("task", "")).strip()
            if not task:
                result = ActionResult(False, messages.CORE_TASK_EMPTY_REPLY)
            else:
                self.store.set_core_task(session.id, task)
                session.core_task = task
                result = ActionResult(True, messages.CORE_TASK_SET_REPLY.format(task=task))
        else:                                        # clear_core_task
            self.store.set_core_task(session.id, "")
            session.core_task = ""
            result = ActionResult(True, messages.CORE_TASK_CLEAR_REPLY)
        self.store.append(session.id, {"role": "tool", "id": tc.id, "name": tc.name,
                                       "content": result.message})
        emit({"type": "tool_result", "name": tc.name, "ok": result.ok, "message": result.message})
        return result

    def _meta_toolbox(self, taken_names: set[str]) -> list[ToolSpec]:
        """内建元工具单（当前只有核心任务两件）。与世界/服务同名冲突时**元工具让位**并记警告
        （对外保持「world 赢」的一致惯例；正常情况下不会撞名）。kind=read：不改世界。"""
        out: list[ToolSpec] = []
        for spec in (messages.CORE_TASK_SET_TOOL, messages.CORE_TASK_CLEAR_TOOL):
            if spec["name"] in taken_names:
                _log.warning("内建元工具与世界/服务工具同名，元工具让位：%s", spec["name"])
                continue
            out.append(ToolSpec(name=spec["name"], description=spec["description"],
                                parameters=spec["parameters"], kind="read"))
        return out

    def _dispatch(self, world, name: str, args: dict, _on_progress=None,
                  _should_abort=None) -> ActionResult:
        if world is None:
            return ActionResult(False, "没连接世界,无法操作。")
        if _on_progress is not None:
            return world.invoke(name, _on_progress=_on_progress, _should_abort=_should_abort, **args)
        return world.invoke(name, **args)

    def _service_toolbox(self, world, world_tool_names: set[str]) -> tuple[list[ToolSpec], dict]:
        """挂载服务的工具单与路由表：tools 并进大脑工具单；routes(name→service) 供分发按来源路由。

        挂载来源 = config.services()（Host 组装，world 不声明服务）；顾问随世界会话出场
        （纯聊天不上服务工具单）——这是 Host 的组装策略，不是 world↔service 的结构绑定。
        - 服务离线/握手失败 → 它的工具这一轮不上单（等它起来即恢复；诚实呈现，不兜底）。
        - 同名冲突 **world 优先**（约定：service 工具名不得与常见世界动作重名），冲突的服务工具
          不上单并记警告——绝不让一个名字有两个去向。"""
        tools: list[ToolSpec] = []
        routes: dict = {}
        if world is None:
            return tools, routes
        for svc in self.registry.mounted_services():
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
    def _system(self, world, has_services: bool = False, core_task: str = "") -> str:
        base = messages.system_prompt()
        if world is None:
            s = base + "\n\n当前:未连接任何世界(纯聊天)。"
            if core_task:
                s += messages.CORE_TASK_BLOCK.format(task=core_task)
            return s
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
        if core_task:   # 核心任务寄存器：状态通道常驻注入，不占历史窗口、无「滑出」概念
            s += messages.CORE_TASK_BLOCK.format(task=core_task)
        return s

    # ==================== 公共接口（签名与 v0.5 一致）====================
    def _init_state(self, session: Session, user_text: str, llm: LLM, max_steps: int,
                    time_budget_s: float) -> LoopState:
        self.store.append(session.id, {"role": "user", "text": user_text})
        # 上一轮遗留的叫停不该殃及这一轮（比如点停止时那轮其实已经自己收尾了）。
        interrupt.clear(session.id)
        return {"session": session, "llm": llm, "max_steps": max_steps,
                "deadline": time.monotonic() + time_budget_s, "step": 0,
                "world": self._world(session), "done": False, "final_reply": "",
                "trace": {"inputs": [], "thinking": [], "reply": "", "brain": session.brain,
                          "model": llm.model}}

    def _graph_config(self, max_steps: int) -> dict:
        # recursion_limit 只是安全带（真正的收口在 act 后的条件边），按图深度放宽到永不误伤。
        return {"recursion_limit": max_steps * _NODES_PER_STEP + 8}

    def handle(self, session: Session, user_text: str, llm: LLM, max_steps: int = DEFAULT_MAX_STEPS,
               time_budget_s: float = DEFAULT_TURN_TIME_BUDGET_S) -> dict:
        state = self._init_state(session, user_text, llm, max_steps, time_budget_s)
        out = self._graph.invoke(state, config=self._graph_config(max_steps))
        return {"reply": out.get("final_reply", ""), "trace": out["trace"],
                "brain": session.brain, "model": llm.model}

    def handle_stream(self, session: Session, user_text: str, llm: LLM,
                      max_steps: int = DEFAULT_MAX_STEPS,
                      time_budget_s: float = DEFAULT_TURN_TIME_BUDGET_S):
        """流式版：节点发的自定义事件（perception/thinking/tool_call/progress/tool_result/reply）
        经 LangGraph custom 流原样转发——事件形状与 v0.5 相同，前端零改动。"""
        state = self._init_state(session, user_text, llm, max_steps, time_budget_s)
        yield {"type": "start", "brain": session.brain, "model": llm.model}
        for ev in self._graph.stream(state, config=self._graph_config(max_steps), stream_mode="custom"):
            yield ev
        yield {"type": "done"}
