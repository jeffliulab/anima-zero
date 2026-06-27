"""ANIMA 展示层后端(通用外壳)。

托管编排器,把前端接到它:给前端「当前世界的感知图」、转发聊天。展示层不认识桌面,只显示世界
给的图。世界是**独立运行的程序**,anima 通过 URL 连它(sim-desk 默认在 :8100);换世界 = 换 URL。
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from dotenv import load_dotenv
from pydantic import BaseModel

from anima import awi_log
from anima.llm import LLM, DEFAULT_BRAIN, list_brains, make_llm
from anima.orchestrator import Orchestrator
from anima.registry import WorldRegistry
from anima.session import SessionStore

# 从 anima-zero/.env 读配置(选脑 / API key / Ollama 地址 / 世界 URL);.env 不入库,模板见 .env.example
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# 世界是独立进程,anima 按 URL 连它;注册时不握手(不硬依赖世界先起)。
# 配置驱动:ANIMA_WORLDS="name=url,name2=url2" 声明世界清单(加世界=加一行配置);
# DEFAULT_WORLD 指定启动默认绑哪个(没设 / 无效就绑清单第一个)。
# 兼容老配置:没设 ANIMA_WORLDS 时,回退用 SIM_DESK_URL 注册并绑定 sim-desk。
def _parse_worlds() -> list[tuple[str, str]]:
    raw = os.getenv("ANIMA_WORLDS", "").strip()
    if not raw:
        return [("sim-desk", os.getenv("SIM_DESK_URL", "http://localhost:8100"))]
    pairs: list[tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        name, url = (s.strip() for s in item.split("=", 1))
        if name and url:
            pairs.append((name, url))
    return pairs


registry = WorldRegistry()
_worlds = _parse_worlds()
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
        _llm_cache[name] = make_llm(name)
    return _llm_cache[name]


# 选哪个大脑在网页里选,挂在会话上;默认值用 factory 的单一来源 DEFAULT_BRAIN(新建会话没选脑时兜底)
_DEFAULT_BRAIN = DEFAULT_BRAIN

# 会话 + 本地记忆;编排器按会话运行(大脑从会话上取)
store = SessionStore()
orchestrator = Orchestrator(registry, store)

SSE_POLL_INTERVAL_S = 0.25  # AWI 流量 SSE 多久查一次新事件;与世界端 world/sim-desk 对齐

# 允许哪些网页源跨域访问;默认只放本机 :3000,设 ANIMA_CORS_ORIGINS=* 可全开(demo 方便)
_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app = FastAPI(title="ANIMA presentation")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/worlds")  # 可连的世界 + 是否在线
def worlds() -> list:
    out = []
    for name in registry.list_worlds():
        w = registry.get(name)
        out.append({
            "name": name,
            "url": getattr(w, "base", ""),
            "online": w.online() if hasattr(w, "online") else True,
        })
    return out


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
                "message": f"未知大脑:{brain}"}
    if not info["available"]:  # 没配好 → 不发请求,直接说清楚
        msg = "未设置 API key" if info["kind"] == "api" else "Ollama 未就绪或模型未拉取"
        return {"ok": False, "reason": "no_key", "model": info["model"],
                "label": info["label"], "message": msg}
    try:
        # 真发一条最小消息(不带图、不进对话历史、绕过编排器),确认 网络 + key + 版本 都通
        get_llm(brain).chat("连通自检,只需回一个字 ok。", [{"role": "user", "text": "ping"}], [], None)
        return {"ok": True, "reason": "", "model": info["model"],
                "label": info["label"], "message": "网络正常"}
    except Exception as e:
        return {"ok": False, "reason": "error", "model": info["model"],
                "label": info["label"], "message": f"{type(e).__name__}: {e}"}


# ---- 会话:同一个世界单活 + 冻结;本地持久化 ----
class NewSessionIn(BaseModel):
    world: str | None = None
    brain: str = _DEFAULT_BRAIN


@app.post("/api/sessions")  # 新建会话(同一个世界的活跃会话会被冻结)
def new_session(inp: NewSessionIn) -> dict:
    return store.new(inp.world, inp.brain).summary()


@app.get("/api/sessions")  # 会话列表 + 状态
def list_sessions() -> list:
    return store.list()


@app.get("/api/sessions/{sid}")  # 看一个会话(冻结的也能看,只读)
def get_session(sid: str) -> dict:
    if not store.exists(sid):
        return {"error": "not found"}
    s = store.get(sid)
    return {**s.summary(), "messages": s.messages}


@app.get("/api/imgfile")  # 取历史感知图(记录里只存路径,前端按 image_ref 来取)
def imgfile(ref: str) -> Response:
    safe = os.path.normpath(os.path.join(store.root, ref))
    if not safe.startswith(store.root) or not safe.endswith(".png") or not os.path.exists(safe):
        return Response(status_code=404)
    return FileResponse(safe, media_type="image/png")


class BrainIn(BaseModel):
    brain: str


@app.post("/api/sessions/{sid}/brain")  # 中途换脑
def set_session_brain(sid: str, inp: BrainIn) -> dict:
    if not store.exists(sid):
        return {"ok": False, "message": "会话不存在"}
    store.set_brain(sid, inp.brain)
    return {"ok": True}


class ChatIn(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")  # 右边聊天(按会话)
def chat(inp: ChatIn) -> dict:
    if not store.exists(inp.session_id):
        return {"reply": "(会话不存在)", "trace": None}
    session = store.get(inp.session_id)
    if session.status != "active":  # 冻结会话只读
        return {"reply": "(这个会话已冻结、只读;请新建一个会话继续。)", "trace": None}
    info = {b["name"]: b for b in list_brains()}.get(session.brain)
    if info is None:
        return {"reply": f"(未知大脑:{session.brain})", "trace": None}
    if not info["available"]:  # 没配置好就别调,直接说清楚
        return {"reply": f"(大脑「{info['label']}」还没配置好,请在 anima-zero/.env 配置后重启后端再用。)",
                "trace": None}
    try:
        return orchestrator.handle(session, inp.message, get_llm(session.brain))
    except Exception as e:  # 大脑调用出错 → 在聊天里如实显示,不让 demo 崩
        return {"reply": f"(大脑调用出错:{type(e).__name__}: {e})", "trace": None}


def _sse(ev: dict) -> str:
    return "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"


@app.post("/api/chat/stream")  # 流式聊天(SSE):边跑边推过程,前端像 ChatGPT 一样滚动展示
def chat_stream(inp: ChatIn) -> StreamingResponse:
    def gen():
        if not store.exists(inp.session_id):
            yield _sse({"type": "reply", "text": "(会话不存在)"})
            yield _sse({"type": "done"})
            return
        session = store.get(inp.session_id)
        if session.status != "active":
            yield _sse({"type": "reply", "text": "(这个会话已冻结、只读;请新建一个会话继续。)"})
            yield _sse({"type": "done"})
            return
        info = {b["name"]: b for b in list_brains()}.get(session.brain)
        if info is None or not info["available"]:
            label = info["label"] if info else session.brain
            yield _sse({"type": "reply", "text": f"(大脑「{label}」还没配置好,请在 anima-zero/.env 配置后重启后端再用。)"})
            yield _sse({"type": "done"})
            return
        try:
            for ev in orchestrator.handle_stream(session, inp.message, get_llm(session.brain)):
                yield _sse(ev)
        except Exception as e:
            yield _sse({"type": "reply", "text": f"(大脑调用出错:{type(e).__name__}: {e})"})
            yield _sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/status")  # 给前端看连接状态
def status() -> dict:
    return {"worlds": registry.list_worlds(), "bound": registry.bound_name()}


# ---- AWI 仪表盘(/awi 页面用)----
@app.get("/api/awi")  # 世界(含能力清单 + 实时 state)+ 大脑 + 会话 + 统计
def awi_overview() -> dict:
    worlds_info = []
    for name in registry.list_worlds():
        w = registry.get(name)
        online = w.online() if hasattr(w, "online") else True
        info = {"name": name, "url": getattr(w, "base", ""), "online": online,
                "version": "", "tools": [], "state": None}
        if online:
            try:
                caps = w.capabilities()  # 命中握手缓存,不再问世界(见 RemoteWorld.capabilities)
                info["version"] = caps.version
                info["tools"] = [
                    {"name": t.name, "description": t.description, "kind": t.kind, "parameters": t.parameters}
                    for t in caps.tools
                ]
                # 状态用「最近一次感知」的缓存,别为了显示又 perceive 一次;从没感知过才播种一次
                st = w.last_state() if hasattr(w, "last_state") else None
                if st is None:
                    st = w.perceive().state
                info["state"] = st
            except Exception:
                info["online"] = False
        worlds_info.append(info)
    return {"worlds": worlds_info, "brains": list_brains(), "sessions": store.list(), "stats": awi_log.stats()}


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
