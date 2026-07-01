"""gazebo-chess 世界服务：把 GazeboChessWorld 经 HTTP(AWI) 暴露成一个标准「世界」。

AWI(脑↔世界): GET /capabilities  GET /perceive  POST /invoke  GET /health
人类页/流(世界本地): GET /stream(MJPEG)  GET /

前提：episode 仿真栈在跑（headless 即可）+ image_bridge 在把相机图桥到 ROS。详见 README / 运行命令.md。
"""
from __future__ import annotations

import asyncio
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
    "怎么把一步棋拆成这些原语，由你的下棋技能按规则算。\n"
    "感知（perceive）只给你相机画面；state 为空 {}（棋盘真值绝不给你，你靠看）。\n"
    "想下棋就进「下棋技能」，别自己乱点单个原语。"
)

# AWI（脑↔世界）走标准 MCP：世界作 MCP server 挂在 /mcp。
mcp_asgi, mcp_lifespan = build_awi_mcp(world, guidance=GAZEBO_GUIDANCE, server_name="gazebo-chess")

app = FastAPI(title="gazebo-chess world", lifespan=mcp_lifespan)
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
@app.get("/stream")
async def stream() -> StreamingResponse:
    async def gen():
        while True:
            jpg = await asyncio.to_thread(world.stream_jpeg)
            if jpg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(1 / config.STREAM_FPS)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(os.path.join(_HERE, "web", "index.html"))
