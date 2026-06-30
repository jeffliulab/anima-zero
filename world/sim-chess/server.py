"""sim-chess 世界服务：把 SimChessWorld 通过 HTTP 暴露成一个标准「世界」(AWI)。

⚠️ 对大脑(ANIMA)只有【双流】：GET /perceive(画面 + 极简 state:{controllers, phase}) 和 GET /stream(MJPEG)；命令结果用 /invoke 的 ok 表达。
  perceive 的 state 只放 controllers + phase，绝不给棋盘结构化真值(局面/FEN/轮次/胜负/棋种)。
AWI(脑↔世界): GET /capabilities  GET /perceive  POST /invoke(take_seat/seat_opponent/start_game/move/resign)  GET /health
人类页/可视化(世界本地，不进 AWI、不动双流): GET /stream  POST /set_controller  POST /start
  POST /resign  POST /click  POST /place  POST /select  POST /reset  POST /switch(切棋种)  GET /status  GET /awi-events  GET /awi-stats  GET /
内置 bot: 后台每拍，只在「比赛中」且当前一方由 bot 控制才自动走。
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from collections import deque

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import render
from world import SimChessWorld

world = SimChessWorld()

# 可调项全部 env 可覆盖（世界独立进程，不 import 脑 config；默认值在此一处）
STREAM_FPS = int(os.getenv("SIMCHESS_STREAM_FPS", "4"))          # 实时画面帧率（棋盘变化慢）
BOT_TICK_S = float(os.getenv("SIMCHESS_BOT_TICK_S", "1.0"))      # 内置 bot 多久检查一次该不该走
SSE_POLL_INTERVAL_S = float(os.getenv("SIMCHESS_SSE_POLL_S", "0.25"))
AWI_LOG_MAXLEN = int(os.getenv("SIMCHESS_AWI_LOG_MAXLEN", "400"))

_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app = FastAPI(title="sim-chess world")
app.add_middleware(CORSMiddleware, allow_origins=_CORS, allow_methods=["*"], allow_headers=["*"])

_HERE = os.path.dirname(os.path.abspath(__file__))

# ---- AWI 流量记账 ----
_LOG: deque = deque(maxlen=AWI_LOG_MAXLEN)
_SEQ = 0
_COUNTS: dict[str, int] = {}


def _log(method: str, summary: str) -> None:
    global _SEQ
    _SEQ += 1
    _COUNTS[method] = _COUNTS.get(method, 0) + 1
    _LOG.append({"id": _SEQ, "ts": time.strftime("%H:%M:%S"), "method": method, "summary": summary})


# ===== AWI（脑↔世界）=====
@app.get("/capabilities")
def capabilities() -> dict:
    caps = world.capabilities()
    _log("capabilities", f"→ {[t['name'] for t in caps['tools']]}")
    return caps


@app.get("/perceive")
def perceive() -> dict:
    state, image_png = world.observe()        # state 只放 controllers(角色 meta)；绝不给棋盘真值
    _log("perceive", "→ 给画面 + controllers")
    return {"state": state, "image_b64": base64.b64encode(image_png).decode()}


class InvokeIn(BaseModel):
    name: str
    args: dict = {}


@app.post("/invoke")
def invoke(inp: InvokeIn) -> dict:
    res = world.invoke(inp.name, **inp.args)   # 只回 {ok, message}
    _log("invoke", f"{inp.name}({inp.args}) → {'success' if res.get('ok') else 'FAIL'}: {res.get('message','')}")
    return res


@app.get("/health")
def health() -> dict:
    return {"ok": True}


# ===== 人类页 / 可视化（世界本地，不进 AWI、不动双流）=====
@app.get("/stream")
async def stream() -> StreamingResponse:
    async def gen():
        while True:
            # render_image 内部已持锁拷贝、出锁渲染；按当前棋种(chess/gomoku)给帧
            jpg = render.to_jpeg(world.render_image())
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(1 / STREAM_FPS)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


class SetControllerIn(BaseModel):
    seat: str
    controller: str | None = None   # 人/anima/bot/空(None)


@app.post("/set_controller")   # 配/换某一席控制者（未开始/暂停/对弈结束时；比赛中要先暂停）
def set_controller(inp: SetControllerIn) -> dict:
    res = world.set_controller(inp.seat, inp.controller)
    _log("setup", f"配座 {inp.seat}={inp.controller or '空'} → {'ok' if res.get('ok') else 'no'}")
    return res


# ===== 生命周期（人类页按钮：requester=human）=====
@app.post("/start")   # 开始 / 开新局
def start() -> dict:
    res = world.start_game()
    _log("setup", f"开始 → {'ok' if res.get('ok') else 'no'}: {res.get('message','')}")
    return res


class ResignIn(BaseModel):
    side: str   # 哪一方认输 white/black


@app.post("/resign")
def resign(inp: ResignIn) -> dict:
    res = world.resign(by="human", side=inp.side)
    _log("setup", f"人认输 {inp.side} → {'ok' if res.get('ok') else 'no'}")
    return res


class ClickIn(BaseModel):
    from_sq: str
    to_sq: str
    promotion: str | None = None


@app.post("/click")
def click(inp: ClickIn) -> dict:
    res = world.human_click_move(inp.from_sq, inp.to_sq, inp.promotion)
    _log("click", f"人 {inp.from_sq}->{inp.to_sq} → {'ok' if res.get('ok') else 'no'}")
    return res


class SelectIn(BaseModel):
    sq: str | None = None


@app.post("/select")   # 人点了起子格：记下来给渲染画高亮圈（不走子）；sq 省略=取消选中
def select(inp: SelectIn) -> dict:
    return world.select_square(inp.sq)


@app.post("/reset")
def reset() -> dict:
    res = world.reset()
    _log("reset", "复位")
    return res


class SwitchIn(BaseModel):
    game: str   # "chess" | "gomoku" | "go"


@app.post("/switch")   # 切换棋种：画面瞬间变（测 ANIMA 对"世界突然换棋盘"的反应）
def switch(inp: SwitchIn) -> dict:
    res = world.switch_game(inp.game)
    _log("setup", f"切棋种 → {inp.game} {'ok' if res.get('ok') else 'no'}")
    return res


class PlaceIn(BaseModel):
    row: int
    col: int


@app.post("/place")   # 五子棋：人在交叉点单击落子
def place(inp: PlaceIn) -> dict:
    res = world.human_place(inp.row, inp.col)
    _log("click", f"人 五子({inp.row},{inp.col}) → {'ok' if res.get('ok') else 'no'}")
    return res


@app.get("/status")
def status() -> dict:
    return world.status()


@app.get("/awi-events")
async def awi_events() -> StreamingResponse:
    async def gen():
        last = 0
        for e in list(_LOG):
            last = e["id"]
            yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
        while True:
            await asyncio.sleep(SSE_POLL_INTERVAL_S)
            for e in [x for x in list(_LOG) if x["id"] > last]:
                last = e["id"]
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/awi-stats")
def awi_stats() -> dict:
    return {"total": _SEQ, "counts": _COUNTS, "last": _LOG[-1] if _LOG else None}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(os.path.join(_HERE, "web", "index.html"))


# ===== 内置 bot 后台循环：当前一方由 bot 控制就自动走 =====
@app.on_event("startup")
async def _bot_loop():
    async def loop():
        while True:
            await asyncio.sleep(BOT_TICK_S)
            try:
                moved = await asyncio.to_thread(world.bot_step)  # 引擎搜索别阻塞事件循环
                if moved:
                    _log("bot", f"内置电脑走 {world.last}")
            except Exception:
                pass

    asyncio.create_task(loop())
