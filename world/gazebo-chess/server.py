"""gazebo-chess 世界服务：把 GazeboChessWorld 经 HTTP(AWI) 暴露成一个标准「世界」。

AWI(脑↔世界): GET /capabilities  GET /perceive  POST /invoke  GET /health
人类页/流(世界本地): GET /stream(MJPEG)  GET /

前提：episode 仿真栈在跑（headless 即可）+ image_bridge 在把相机图桥到 ROS。详见 README / 运行命令.md。
"""
from __future__ import annotations

import asyncio
import base64
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import config
from world import GazeboChessWorld

_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
_HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="gazebo-chess world")
app.add_middleware(CORSMiddleware, allow_origins=_CORS, allow_methods=["*"], allow_headers=["*"])

world = GazeboChessWorld()


# ===== AWI（脑↔世界）=====
@app.get("/capabilities")
def capabilities() -> dict:
    return world.capabilities()


@app.get("/perceive")
def perceive() -> dict:
    state, image_png = world.observe()
    return {"state": state,
            "image_b64": base64.b64encode(image_png).decode() if image_png else None}


class InvokeIn(BaseModel):
    name: str
    args: dict = {}


@app.post("/invoke")
def invoke(inp: InvokeIn) -> dict:
    return world.invoke(inp.name, **inp.args)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "arm_ready": world.ready}


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
