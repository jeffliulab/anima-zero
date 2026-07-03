"""gazebo-chess 世界服务：把 GazeboChessWorld 经 HTTP(AWI) 暴露成一个标准「世界」。

AWI(脑↔世界): GET /capabilities  GET /perceive  POST /invoke  GET /health
人类页/流(世界本地): GET /stream(MJPEG)  GET /

前提：episode 仿真栈在跑（headless 即可）+ image_bridge 在把相机图桥到 ROS。详见 README / 运行命令.md。
"""
from __future__ import annotations

import asyncio
import contextlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

import config
from awi_mcp import build_awi_mcp
from world import GazeboChessWorld

_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
_HERE = os.path.dirname(os.path.abspath(__file__))

world = GazeboChessWorld()

# 世界说明书（= MCP prompt "guidance"；大脑读了就懂怎么跟我打交道）。
GAZEBO_GUIDANCE = (
    "我是「gazebo-chess」世界：Gazebo 里的物理国际象棋盘 + 一条真机械臂。我只管【物理执行】，"
    "不懂棋规、不判输赢——那是你（大脑）的事。\n"
    "我给你三个物理原语：move（把一个子从 from 格夹到 to 格）、remove（把某格的子夹走丢进弃子区）、"
    "place（在某格摆上一个新子）。吃子=先 remove 再 move；升变=move+remove+place；易位=两次 move——"
    "怎么把一步棋拆成这些原语，由你自己按棋规想清楚、按顺序逐个调用。\n"
    "感知（perceive）给你**多路相机画面**（默认两路：oblique 斜视、overhead 正俯视——"
    "state.cameras 按序标注每张图是哪路相机），除相机名单外 state 不含任何东西（棋盘真值绝不给你，你靠看）。\n"
    "一个原语要几十秒（真机械臂在动），失败了看我的报错决定怎么补救。"
)

# 挂载服务声明：本世界配套的纯计算顾问（象棋引擎）——world+service 一起设计，配对关系属于应用侧，
# 所以由世界声明（大脑握手读 anima://services 自动连接）；URL 走本世界自带 env。
GZCHESS_SERVICES = [{"name": "chess-engine",
                     "url": os.getenv("GZCHESS_ENGINE_URL", "http://localhost:8108")}]

# AWI（脑↔世界）走标准 MCP：世界作 MCP server 挂在 /mcp。
mcp_asgi, mcp_lifespan = build_awi_mcp(world, guidance=GAZEBO_GUIDANCE,
                                       services=GZCHESS_SERVICES, server_name="gazebo-chess")

# lifespan：包住 MCP 的 lifespan，进程退出时把本世界 spawn 的相机模型删净——
# uvicorn 重启/热重载也走这里，防「残留相机抢同一话题 → 画面交替混流」（2026-07-02 实锤根因之一）。
@contextlib.asynccontextmanager
async def _lifespan(app):
    async with mcp_lifespan(app):
        try:
            yield
        finally:
            await asyncio.to_thread(world.cleanup_cameras)


app = FastAPI(title="gazebo-chess world", lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_CORS, allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp_asgi)   # 大脑经此 list_tools / read_resource(感知) / call_tool / get_prompt(说明书)


# ===== AWI（脑↔世界）现在走标准 MCP（挂在 /mcp）；旧的 /capabilities /perceive /invoke 已撤 =====


@app.get("/health")
def health() -> dict:
    return {"ok": True, "arm_ready": world.ready}


@app.get("/status")  # 人类调试台·世界真值（上帝视角）：走世界本地，不进 AWI、绝不给 ANIMA
def status() -> dict:
    return world.debug_state()


# ===== 人类页 / 流（世界本地，不进 AWI）=====
@app.get("/streams")  # 有哪几路相机直播（前端据此并列展示多画面；单相机世界没有此端点=回退单 /stream）
def streams() -> list[dict]:
    return [{"name": n, "url": f"/stream?cam={n}"} for n in config.cam_names()]


@app.get("/stream")   # 某一路相机的 MJPEG 直播；?cam=<名字>，缺省=第一路
async def stream(cam: str = "") -> StreamingResponse:
    async def gen():
        while True:
            jpg = await asyncio.to_thread(world.stream_jpeg, cam)
            if jpg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(1 / config.STREAM_FPS)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(os.path.join(_HERE, "web", "index.html"))
