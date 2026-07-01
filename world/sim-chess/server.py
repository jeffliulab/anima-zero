"""sim-chess 世界服务：把 SimChessWorld 暴露成一个标准「世界」。

⚠️ 对大脑(ANIMA)：AWI 走标准 **MCP**（挂在 /mcp）——只有一个动作 `move`，perceive 只给画面、state 空 {}，
  绝不给棋盘真值(局面/FEN/轮次/胜负/棋种)。旧的开局仪式(take_seat/seat_opponent/start_game/resign)+phase+
  controllers 已撤（见 world.py）。命令结果用 MCP tools/call 的 ok 表达。
人类页/可视化(世界本地，不进 AWI、带外): GET /stream  POST /bot_side(配内置电脑走哪方)  POST /click  POST /place
  POST /select  POST /reset(开新局)  POST /switch(切棋种)  POST /resign  GET /status  GET /awi-events  GET /awi-stats  GET /
内置电脑: 后台每拍，轮到 bot_side 那一方且未终局就自动走。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections import deque

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import render
from awi_mcp import build_awi_mcp
from world import SimChessWorld

world = SimChessWorld()

# 世界说明书（= MCP prompt "guidance"；大脑读了就懂怎么跟我打交道）。
SIMCHESS_GUIDANCE = (
    "我是「sim-chess」世界：一张真国际象棋盘。我握真值、判合法、判胜负；对你（大脑）我**只给画面**，"
    "不告诉你局面/FEN/轮次/胜负——你全靠看。\n"
    "你只有一个动作 `move`（from→to，可带 piece/promotion）：查合法→落子。轮到谁走由走子合法性天然管"
    "（白子只能白方回合走），你靠自己看画面判断该不该出手；不用先选边、不用开局、没有阶段。\n"
    "对手（人 / 内置电脑）是我网页上的事，不归你管：人会在我网页点子走，或开一个内置电脑走某一方。\n"
    "想下棋就进「下棋技能」，用 move 走子；对手走了你靠看画面认出来。"
)

# 可调项全部 env 可覆盖（世界独立进程，不 import 脑 config；默认值在此一处）
STREAM_FPS = int(os.getenv("SIMCHESS_STREAM_FPS", "4"))          # 实时画面帧率（棋盘变化慢）
BOT_TICK_S = float(os.getenv("SIMCHESS_BOT_TICK_S", "1.0"))      # 内置电脑多久检查一次该不该走
SSE_POLL_INTERVAL_S = float(os.getenv("SIMCHESS_SSE_POLL_S", "0.25"))
AWI_LOG_MAXLEN = int(os.getenv("SIMCHESS_AWI_LOG_MAXLEN", "400"))

_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# AWI（脑↔世界）走标准 MCP：世界作 MCP server 挂在 /mcp。
mcp_asgi, mcp_lifespan = build_awi_mcp(world, guidance=SIMCHESS_GUIDANCE, server_name="sim-chess")


@contextlib.asynccontextmanager
async def _lifespan(app):
    """MCP session manager + 内置电脑后台循环，一起在 app 生命周期内跑。
    （FastAPI 传了 lifespan 后 @on_event 会被忽略，故把 bot loop 并进来。）"""
    async with mcp_lifespan(app):
        async def _bot_loop():
            while True:
                await asyncio.sleep(BOT_TICK_S)
                try:
                    if await asyncio.to_thread(world.bot_step):   # 引擎搜索别阻塞事件循环
                        _log("bot", f"内置电脑走 {world.last}")
                except Exception:
                    pass
        task = asyncio.create_task(_bot_loop())
        try:
            yield
        finally:
            task.cancel()


app = FastAPI(title="sim-chess world", lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_CORS, allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp_asgi)   # 大脑经此 list_tools / read_resource(感知) / call_tool / get_prompt(说明书)

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


# ===== AWI（脑↔世界）现在走标准 MCP（挂在 /mcp）；旧的 /capabilities /perceive /invoke 已撤 =====


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


class BotSideIn(BaseModel):
    side: str | None = None   # 内置电脑走哪方：white/black/None(无)


@app.post("/bot_side")   # 网页配「内置电脑走哪方」（替掉旧的配座 /set_controller + /start）
def bot_side(inp: BotSideIn) -> dict:
    res = world.set_bot_side(inp.side)
    _log("setup", f"内置电脑 → {inp.side or '无'} {'ok' if res.get('ok') else 'no'}")
    return res


class ResignIn(BaseModel):
    side: str   # 哪一方认输 white/black


@app.post("/resign")
def resign(inp: ResignIn) -> dict:
    res = world.resign(inp.side)
    _log("setup", f"认输 {inp.side} → {'ok' if res.get('ok') else 'no'}")
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

# （内置电脑后台循环已并入上面的 _lifespan——FastAPI 传 lifespan 后 @on_event 会被忽略。）
