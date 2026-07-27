"""ANIMA 展示层后端(通用外壳)。

托管编排器,把前端接到它:给前端「当前世界的感知图」、转发聊天。展示层不认识桌面,只显示世界
给的图。世界是**独立运行的程序**,anima 通过 URL 连它(sim-desk 默认在 :8100);换世界 = 换 URL。
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from dotenv import load_dotenv
from pydantic import BaseModel

from anima import awi_log, config, messages, paths, session_log
from anima.llm import LLM, DEFAULT_BRAIN, list_brains, make_llm
from anima.session.session_log import LoggingLLM, bound_stream, session_scope
from anima.core import interrupt
from anima.core.orchestrator import Orchestrator
from anima.clients.registry import WorldRegistry
from anima.session import SessionStore

# 从 anima-zero/.env 读配置(选脑 / API key / Ollama 地址 / 世界 URL);.env 不入库,模板见 .env.example。
# 路径统一走 anima.paths（迁进 src/presentation 后不能再靠 __file__+".." 猜仓库根）。
load_dotenv(paths.ENV_FILE)

# 世界是独立进程,anima 按 URL 连它;注册时不握手(不硬依赖世界先起)。
# 世界清单的单一来源在 config.worlds()（ANIMA_WORLDS env 覆盖；默认含所有已知世界，追加不替换——T0）；
# DEFAULT_WORLD 指定启动默认绑哪个(没设 / 无效就绑清单第一个)。
registry = WorldRegistry()
_worlds = config.worlds()
for _name, _url in _worlds:
    registry.register_world(_name, _url)
_default_world = os.getenv("DEFAULT_WORLD", "").strip()
if not _default_world or registry.get(_default_world) is None:
    _default_world = _worlds[0][0] if _worlds else ""
if _default_world:
    registry.bind(_default_world)  # demo 方便:启动即绑一个世界(此处不发 HTTP)

# 大脑按需构造并缓存(每个脑一份);对话时按前端选择切换 orchestrator.llm
_llm_cache: dict[str, LLM] = {}


def get_llm(name: str) -> LLM:
    if name not in _llm_cache:
        # 收口：所有 LLM 调用都经这里构造 → 包一层 LoggingLLM，llm_call 留痕进统一日志（Session Logs 页看）
        _llm_cache[name] = LoggingLLM(make_llm(name), name)
    return _llm_cache[name]


# 选哪个大脑在网页里选,挂在会话上;默认值用 factory 的单一来源 DEFAULT_BRAIN(新建会话没选脑时兜底)
_DEFAULT_BRAIN = DEFAULT_BRAIN

# 会话 + 本地记忆;编排器按会话运行(大脑从会话上取)
store = SessionStore()
orchestrator = Orchestrator(registry, store)

SSE_POLL_INTERVAL_S = config.AWI_POLL_INTERVAL_S  # AWI 流量 SSE 多久查一次新事件(config 单一来源,删 inline 魔法数)

# 允许哪些网页源跨域访问;默认只放本机 :3000,设 ANIMA_CORS_ORIGINS=* 可全开(demo 方便)
_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app = FastAPI(title="ANIMA presentation")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/worlds")  # 可连的世界 + 是否在线 + 是否已审批
def worlds() -> list:
    out = []
    for name in registry.list_worlds():
        w = registry.get(name)
        online = w.online() if hasattr(w, "online") else True
        # 信任状态要和在线状态并列显示：一个世界可以「在线但没批准」，那时它列得出来、
        # 却驱动不了——不把这个状态说出来，用户只会看到一个莫名其妙没有工具的世界。
        # 世界不在线时不去问（问就要握手，等超时），状态留空。
        trust_state = ""
        if online:
            try:
                trust_state = w.trust_decision().state
            except Exception:
                trust_state = ""
        out.append({
            "name": name,
            "url": getattr(w, "base", ""),
            "online": online,
            "trust": trust_state,          # unknown / changed / trusted / ""(问不到)
        })
    return out


# ---- 世界信任（v1.1）----
# 世界的说明书会进系统提示词、工具描述会进工具单——都是远端写的文本。所以在操作者亲眼看过并
# 批准之前，这些内容不进大脑（见 core/trust.py 与 clients/world_client.py 的信任闸）。
# 这两个端点就是那道人类审批：一个把**完整原文**摊出来给人看，一个记下他的决定。

@app.get("/api/worlds/{name}/manifest")  # 待审阅的完整清单（给人看，不是给大脑看）
def world_manifest(name: str) -> dict:
    w = registry.get(name)
    if w is None:
        return {"ok": False, "message": f"No world named {name!r}."}
    try:
        d = w.trust_decision()
        raw = w.raw_capabilities()
    except Exception as e:
        return {"ok": False, "message": f"Cannot reach this world, so its manifest is unavailable: {e}"}
    return {
        "ok": True,
        "state": d.state,
        "reason": d.reason,
        "changes": d.changes,          # state=changed 时：这次和上次批准的差在哪
        "url": getattr(w, "base", ""),
        # ⛔ 摊给人看的必须是**未经过滤的原文**——审批时看到的东西如果和被审批的东西不是同一个，
        #    这次审批就没有意义了。
        "guidance": raw.guidance,
        "tools": [{"name": t.name, "kind": t.kind, "description": t.description,
                   "parameters": t.parameters} for t in raw.tools],
    }


@app.post("/api/worlds/{name}/approve")  # 记下操作者对当前这份清单的批准
def approve_world(name: str) -> dict:
    w = registry.get(name)
    if w is None:
        return {"ok": False, "message": f"No world named {name!r}."}
    try:
        h = w.approve()
    except Exception as e:
        return {"ok": False, "message": f"Approval failed: {e}"}
    return {"ok": True, "hash": h,
            "message": f"Approved the current manifest of the world {name!r}. "
                       f"If it changes again you will be asked afresh."}


# ---- 世界配置（v1.0 的 AWI 新通道）----
# 世界经 AWI **声明**它能配什么（大脑握手时读到，见 world_client）；**改**它走世界本地的
# 带外 HTTP。后端这两个端点只是转发 + 改完让大脑重新握手，自己不理解任何具体配置项。
# ⛔ 通用：不认识 body/机器人/任何键名——世界声明什么就转发什么，网页照着渲染。

@app.get("/api/worlds/{name}/config")  # 这个世界能配什么、现在是什么
def world_config(name: str) -> dict:
    w = registry.get(name)
    if w is None:
        return {"ok": False, "message": f"No world named {name!r}.", "options": []}
    try:
        return {"ok": True, **(w.capabilities().config or {"options": []})}
    except Exception as e:
        return {"ok": False, "message": f"Cannot read this world's configuration: {e}", "options": []}


@app.post("/api/worlds/{name}/config")  # 改配置（如换身体）
def set_world_config(name: str, body: dict) -> dict:
    w = registry.get(name)
    if w is None:
        return {"ok": False, "message": f"No world named {name!r}."}
    try:
        r = w.set_config(str(body.get("key", "")), str(body.get("value", "")))
    except Exception as e:
        return {"ok": False, "message": f"Changing the configuration failed: {e}"}
    # 改完必须重新握手：换了配置，世界的工具单/说明书都可能变了。
    # ⛔ 不重新握手就是 v0.9 那个坑——大脑握着旧的能力清单，新工具永远上不了工具单。
    if r.get("ok"):
        w.refresh()
    return r


@app.post("/api/worlds/{name}/refresh")  # 重新握手：丢掉能力缓存，下次现问世界
def refresh_world(name: str) -> dict:
    """世界那边改了工具 / 重启了，让大脑重新问一遍。

    背景（v0.9 踩的坑，值得一个端点）：`RemoteWorld` 在首次握手时缓存世界的能力清单、
    之后不再重问。世界加了新工具、后端没重启 → 新工具**永远**上不了 LLM 的工具单。
    上一版新增的环视就这么被藏了七次实验，还一度被误判成"模型不想用"。
    """
    w = registry.get(name)
    if w is None:
        return {"ok": False, "message": f"No world named {name!r}."}
    w.refresh()
    try:
        caps = w.capabilities()
        return {"ok": True, "message": f"Handshake redone; it now offers {len(caps.tools)} tool(s).",
                "tools": [t.name for t in caps.tools]}
    except Exception as e:
        return {"ok": False, "message": f"Handshake failed — the world may not be running: {e}"}


@app.get("/api/perceive")  # 左边传感区:显示当前会话所连世界的图
def perceive(session_id: str | None = None) -> Response:
    if session_id and store.exists(session_id):
        s = store.get(session_id)
        w = registry.get(s.world) if s.world else None
    else:
        w = registry.current_or_none()  # 没给 session_id 时退回默认绑定的世界
    if w is None:
        return Response(status_code=204)  # 没连世界 → 没画面(纯聊天)
    try:
        return Response(content=w.perceive().image_png, media_type="image/png")
    except Exception:
        return Response(status_code=204)  # 世界没起 / 断了 → 暂时没画面


@app.get("/api/brains")  # 给前端选择器:五个大脑 + 版本号 + 各自是否配置好
def brains() -> dict:
    return {"brains": list_brains(), "default": _DEFAULT_BRAIN}


@app.get("/api/check")  # 连通自检:前端选完大脑,试探它能不能连上
def check(brain: str) -> dict:
    info = {b["name"]: b for b in list_brains()}.get(brain)
    if info is None:
        return {"ok": False, "reason": "unknown", "model": "", "label": brain,
                "message": f"Unknown brain: {brain}"}
    if not info["available"]:  # 没配好 → 不发请求,直接说清楚
        msg = ("No API key configured" if info["hosting"] == "api"
               else "Ollama is not ready, or the model has not been pulled")
        return {"ok": False, "reason": "no_key", "model": info["model"],
                "label": info["label"], "message": msg}
    try:
        # 真发一条最小消息(不带图、不进对话历史、绕过编排器),确认 网络 + key + 版本 都通
        get_llm(brain).chat("Connectivity check. Reply with the single word ok.", [{"role": "user", "text": "ping"}], [], None)
        return {"ok": True, "reason": "", "model": info["model"],
                "label": info["label"], "message": "Reachable"}
    except Exception as e:
        return {"ok": False, "reason": "error", "model": info["model"],
                "label": info["label"], "message": f"{type(e).__name__}: {e}"}


# ---- 会话:同一个世界单活 + 冻结;本地持久化 ----
class NewSessionIn(BaseModel):
    world: str | None = None
    brain: str = _DEFAULT_BRAIN


@app.post("/api/sessions")  # 新建会话(同一个世界的活跃会话会被冻结)
def new_session(inp: NewSessionIn) -> dict:
    s, _frozen = store.new(inp.world, inp.brain)
    return s.summary()


@app.get("/api/sessions")  # 会话列表 + 状态
def list_sessions() -> list:
    return store.list()


@app.get("/api/sessions/{sid}")  # 看一个会话(冻结的也能看,只读)
def get_session(sid: str) -> dict:
    if not store.exists(sid):
        return {"error": "not found"}
    s = store.get(sid)
    return {**s.summary(), "messages": s.messages}


@app.delete("/api/sessions/{sid}")  # 删一个会话(删磁盘记录)
def delete_session(sid: str) -> dict:
    deleted = store.delete(sid)
    return {"ok": deleted}


@app.get("/api/imgfile")  # 取历史感知图(记录里只存路径,前端按 image_ref 来取)
def imgfile(ref: str) -> Response:
    safe = os.path.normpath(os.path.join(store.root, ref))
    if not safe.startswith(store.root) or not safe.endswith(".png") or not os.path.exists(safe):
        return Response(status_code=404)
    return FileResponse(safe, media_type="image/png")


class BrainIn(BaseModel):
    brain: str


@app.post("/api/sessions/{sid}/interrupt")  # 叫停这个会话正在跑的那一轮（网页「停止」按钮）
def interrupt_session(sid: str) -> dict:
    """置一个进程内的叫停旗标；主循环下一个检查点（含动作等待期）就收尾。

    立刻返回、不等那一轮真的停——世界那边正在做的那一步还得做完（物理动作没法瞬间撤回），
    前端据此显示「停止中…」。停下来是**可续的停顿**：核心任务留在册，说「继续」就接着来。
    """
    if not store.exists(sid):
        return {"ok": False, "message": "(no such session)"}
    interrupt.request(sid)
    return {"ok": True}


@app.post("/api/sessions/{sid}/brain")  # 中途换脑
def set_session_brain(sid: str, inp: BrainIn) -> dict:
    if not store.exists(sid):
        return {"ok": False, "message": "No such session"}
    store.set_brain(sid, inp.brain)
    return {"ok": True}


class ChatIn(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")  # 右边聊天(按会话)
def chat(inp: ChatIn) -> dict:
    if not store.exists(inp.session_id):
        return {"reply": "(No such session.)", "trace": None}
    session = store.get(inp.session_id)
    if session.status != "active":  # 冻结会话只读
        return {"reply": "(This session is frozen and read-only. Start a new session to carry on.)", "trace": None}
    # 进入/退出/暂停对弈的判断都已收口到 orchestrator（元控制器），这里不再拦截。
    info = {b["name"]: b for b in list_brains()}.get(session.brain)
    if info is None:
        return {"reply": messages.UNKNOWN_BRAIN_REPLY.format(brain=session.brain), "trace": None}
    if not info["available"]:  # 没配置好就别调,直接说清楚
        return {"reply": messages.BRAIN_NOT_CONFIGURED_REPLY.format(brain=info["label"]),
                "trace": None}
    try:
        with session_scope(inp.session_id):   # 这次请求的全部留痕（LLM/世界/服务）都标上 session（Session Logs 可筛）
            return orchestrator.handle(session, inp.message, get_llm(session.brain))
    except Exception as e:  # 大脑调用出错 → 在聊天里如实显示,不让 demo 崩
        return {"reply": messages.BRAIN_CALL_FAILED_REPLY.format(error=f"{type(e).__name__}: {e}"), "trace": None}


def _sse(ev: dict) -> str:
    return "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"


@app.post("/api/chat/stream")  # 流式聊天(SSE):边跑边推过程,前端像 ChatGPT 一样滚动展示
def chat_stream(inp: ChatIn) -> StreamingResponse:
    def gen():
        if not store.exists(inp.session_id):
            yield _sse({"type": "reply", "text": "(No such session.)"})
            yield _sse({"type": "done"})
            return
        session = store.get(inp.session_id)
        if session.status != "active":
            yield _sse({"type": "reply", "text": "(This session is frozen and read-only. Start a new session to carry on.)"})
            yield _sse({"type": "done"})
            return
        info = {b["name"]: b for b in list_brains()}.get(session.brain)
        if info is None or not info["available"]:
            label = info["label"] if info else session.brain
            yield _sse({"type": "reply", "text": messages.BRAIN_NOT_CONFIGURED_REPLY.format(brain=label)})
            yield _sse({"type": "done"})
            return
        try:
            for ev in orchestrator.handle_stream(session, inp.message, get_llm(session.brain)):
                yield _sse(ev)
        except Exception as e:
            yield _sse({"type": "reply", "text": messages.BRAIN_CALL_FAILED_REPLY.format(error=f"{type(e).__name__}: {e}")})
            yield _sse({"type": "done"})

    # bound_stream 给整条生成器套上一个带 session 的固定上下文逐步迭代——保证流式期间每次 LLM 调用
    # 都读得到 session、正确写进 session-<id>.jsonl。详见 session_log.bound_stream。
    return StreamingResponse(bound_stream(inp.session_id, gen()), media_type="text/event-stream")


@app.get("/api/status")  # 给前端看连接状态
def status() -> dict:
    return {"worlds": registry.list_worlds(), "bound": registry.bound_name()}


@app.get("/api/config")  # 核心运行参数（网页左下角常驻显示）
def runtime_config() -> dict:
    """当前生效的核心运行参数 + 各自的 env 名与说明。

    ⛔ 值/env 名/说明全部现读自 `config.Settings` 的字段定义——网页只是它的显示器，
    一个数字都不许在前端写死（写两份必然出现"网页显示 60、.env 里是 8"的对不上账）。
    只读：改参数走 .env + 重启，config.py 保持单一来源。
    """
    return {"params": config.runtime_params()}


# ---- AWI 仪表盘(/awi 页面用)----
# ---- 挂载服务（顾问）卡片：Host 组装——由 ANIMA 按 config.services() 挂载（经 registry 建/复用客户端）----
# service 和 world 在 MCP 里都是"一个 server"，只是 service 是纯计算 tool server：只有 tools，
# 无感知(resource)、无说明书(prompt)。能力清单由 RemoteService 缓存（握手一次）。
def _service_servers() -> list[dict]:
    out: list[dict] = []
    for svc in registry.mounted_services():
        info = {"name": svc.name, "url": svc.base, "kind": "service",
                "online": svc.online(), "tools": []}
        if info["online"]:
            try:
                info["tools"] = [
                    {"name": t.name, "description": t.description, "kind": t.kind,
                     "parameters": t.parameters}
                    for t in svc.capabilities().tools]
            except Exception:
                info["online"] = False
        out.append(info)
    return out


@app.get("/api/awi")  # 世界 + 引擎 server(含能力清单 + 实时 state)+ 大脑 + 会话 + 统计
def awi_overview() -> dict:
    worlds_info = []
    for name in registry.list_worlds():
        w = registry.get(name)
        online = w.online() if hasattr(w, "online") else True
        info = {"name": name, "url": getattr(w, "base", ""), "kind": "world", "online": online,
                "version": "", "tools": [], "state": None, "status": None, "state_schema": {},
                "guidance": "", "config": {}, "trust": ""}
        if online:
            try:
                caps = w.capabilities()  # 命中握手缓存,不再问世界(见 RemoteWorld.capabilities)
                # 信任状态要和能力一起给：面板显示的 tools / guidance 是**过滤后**的，
                # 未批准的世界这两栏是空的。不把状态一起说出来，看的人只会以为这个世界坏了。
                info["trust"] = w.trust_decision().state if hasattr(w, "trust_decision") else ""
                info["version"] = caps.version
                info["tools"] = [
                    {"name": t.name, "description": t.description, "kind": t.kind, "parameters": t.parameters}
                    for t in caps.tools
                ]
                # state_schema = 世界【声明】的 perceive.state 契约(键名+含义)。面板据此显示,不靠缓存 perceive 猜。
                info["state_schema"] = caps.state_schema
                # guidance = 世界的「说明书」(= MCP prompt)。面板第四区 GUIDANCE 显示;大脑也读它进系统提示。
                info["guidance"] = caps.guidance
                # config = 世界声明的可配置项(v1.0 新通道)。面板据此渲染一个下拉;改它走带外 HTTP。
                info["config"] = caps.config or {}
                # status = 世界自身的真实状态(仅人看的调试台,走世界本地 /status,人的上帝视角),绝不给 ANIMA。
                # 这跟 ANIMA 的 perceive 明确分开:sim-chess 的真值(局面/轮次/胜负)藏在 /status、绝不进 perceive。
                # 没有 /status 的世界(如 sim-desk,它的 perceive 本就是真值)→ 回退到 perceive 的 state。
                truth = w.debug_state() if hasattr(w, "debug_state") else None
                if truth is None:
                    truth = w.last_state() if hasattr(w, "last_state") else None
                    if truth is None:
                        truth = w.perceive().state
                info["status"] = truth
                # state = ANIMA 上一次 perceive 真正收到的结构化 state(用缓存,不额外 perceive、不刷流量)。
                # 这是「world 向 ANIMA 传输的唯一结构化东西」——卡片里单独、显眼地展示它。
                info["state"] = w.last_state() if hasattr(w, "last_state") else None
            except Exception:
                info["online"] = False
        worlds_info.append(info)
    return {"worlds": worlds_info, "services": _service_servers(),
            "brains": list_brains(), "sessions": store.list(), "stats": awi_log.stats()}


@app.get("/api/awi/events")  # AWI 实时流量(SSE):ANIMA↔世界 每次调用
async def awi_events_stream() -> StreamingResponse:
    async def gen():
        last = 0
        for e in awi_log.recent(0):
            last = e["id"]
            yield _sse(e)
        while True:
            await asyncio.sleep(SSE_POLL_INTERVAL_S)
            for e in awi_log.recent(last):
                last = e["id"]
                yield _sse(e)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/session-logs")  # Session Logs：本会话全部行为流水（llm_call / world_call / service_call 按时间合并）
def session_logs(limit: int = 500, session: str = "") -> dict:
    return {"entries": session_log.recent(limit, session), "sessions": session_log.sessions()}


# ---- 开发自测接口（config.DEV_API=1 才开；默认关，生产/演示环境不暴露）----
class DevTurnIn(BaseModel):
    world: str | None = None       # 新建会话连哪个世界（复用 session_id 时忽略）
    message: str
    brain: str = ""                # 空=默认脑
    session_id: str | None = None  # 传了就在既有会话上续一轮


@app.post("/api/dev/turn")  # 跑完整一轮对话，返回回复 + 该轮新增的全部 Session Logs 流水
def dev_turn(inp: DevTurnIn) -> dict:
    """开发者/agent 自测钩子：一次调用拿到「回复 + llm_call/world_call/service_call 完整链」，
    可直接断言行为（如 best_move→move 两连跳）。要求目标世界/服务已在跑。"""
    if not config.DEV_API:
        return {"error": "The dev API is off. Set ANIMA_DEV_API=1 and restart the backend "
                        "(development only)."}
    if inp.session_id and store.exists(inp.session_id):
        session = store.get(inp.session_id)
    else:
        session, _ = store.new(inp.world, inp.brain or _DEFAULT_BRAIN)
    prior = session_log.recent(1, session=session.id)
    marker = (prior[-1].get("t", 0.0), prior[-1].get("id", 0)) if prior else (0.0, 0)
    with session_scope(session.id):
        out = orchestrator.handle(session, inp.message, get_llm(session.brain))
    log = [e for e in session_log.recent(1000, session=session.id)
           if (e.get("t", 0.0), e.get("id", 0)) > marker]
    return {"session_id": session.id, "reply": out["reply"], "log": log}




# ================================ the web app, when it travels with us / 随包同行的网页 ===
# The wheel can carry a pre-built copy of the web app, so `pip install anima` gives you a
# usable interface on a machine with no node. It is mounted **last**, on purpose: every
# /api/... route above is registered first, so a catch-all here can never shadow one.
#
# Absent in a source checkout until `python scripts/build_ui.py` has been run — which is why
# this is a quiet no-op rather than an error. Missing UI is a normal state during backend
# development, not a fault.
#
# wheel 里可以带一份预先构建好的网页，好让 `pip install anima` 在一台没有 node 的机器上也有可用界面。
# 它**有意挂在最后**：上面每一条 /api/... 路由都先注册了，所以这里的兜底路由不可能盖住它们。
#
# 在源码检出里，`python scripts/build_ui.py` 跑过之前它是不存在的——所以这里是**安静地不挂载**
# 而不是报错。后端开发时没有网页是正常状态，不是故障。
_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def ui_build_time() -> str | None:
    """When the bundled web app was built, or None if there is none.

    ⚠️ Printed on startup for one reason: a wheel built without running the UI build
    silently ships whatever copy happened to be lying around, and a stale interface looks
    exactly like a working one. A visible timestamp is the cheapest way to notice.

    随包的网页是什么时候构建的；没有网页则为 None。

    ⚠️ 启动时打印它只为一件事：构建 wheel 时忘了先构建网页，就会**静默**地把碰巧留在那儿的旧版本
    发出去，而一个过时的界面看起来和正常的一模一样。打一个看得见的时间戳，是最便宜的发现办法。
    """
    index = os.path.join(_UI_DIR, "index.html")
    if not os.path.exists(index):
        return None
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(index)))


if os.path.isdir(_UI_DIR):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_UI_DIR, html=True), name="web")
