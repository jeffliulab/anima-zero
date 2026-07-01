"""camera 世界服务：把 CameraWorld 通过 HTTP 暴露成一个标准「世界」(AWI)。

⚠️ 对大脑(ANIMA)只有【看】：GET /perceive(画面 + 极简 state) 和 GET /stream(MJPEG)。
  capabilities 的 tools 为空 → 大脑没有任何动作可调（"只能看、不能操作"由此保证）。
AWI(脑↔世界): GET /capabilities  GET /perceive  POST /invoke(一律拒绝)  GET /health
人类页/控制(世界本地，不进 AWI、与大脑解耦): GET /stream  GET /cameras  POST /select  POST /release  GET /status  GET /

设计要点：服务启动**不主动打开任何摄像头**；真正打开硬件，发生在人在世界页下拉框选定某个摄像头、
POST /select 那一下。这把"碰硬件"那一步交到了人手里。
"""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from awi_mcp import build_awi_mcp
from world import CameraWorld

world = CameraWorld()

# 世界说明书（= MCP prompt "guidance"；大脑读了就懂怎么跟我打交道）。
CAMERA_GUIDANCE = (
    "我是「摄像头」世界：一个只读的真实相机画面源。我没有任何可调动作（tools 为空）——你只能【看】、不能操作。\n"
    "感知（perceive）给你当前选中摄像头的画面；state 为空 {}。没选摄像头 / 抓不到画面时我不给图（你会看到没有画面），"
    "我绝不伪造一张。\n"
    "想让我出画面，需要人在我的网页上从下拉框选一个摄像头（连接硬件那一步交给人做），不是你能调的。"
)

# 可调项 env 可覆盖（世界独立进程，不 import 脑 config；默认值在此一处）。
STREAM_FPS = int(os.getenv("CAMERA_STREAM_FPS", "15"))   # 实时画面帧率

_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# AWI（脑↔世界）现在走标准 MCP：世界作为 MCP server 挂在 /mcp（tools/resources/prompts）。
mcp_asgi, mcp_lifespan = build_awi_mcp(world, guidance=CAMERA_GUIDANCE, server_name="camera")

app = FastAPI(title="camera world", lifespan=mcp_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_CORS, allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp_asgi)   # 大脑经此 list_tools / read_resource(感知) / call_tool / get_prompt(说明书)

_HERE = os.path.dirname(os.path.abspath(__file__))


@app.get("/health")
def health() -> dict:
    return {"ok": True}


# ===== 人类页 / 控制（世界本地，不进 AWI、与大脑解耦）=====
@app.get("/stream")
async def stream() -> StreamingResponse:
    async def gen():
        while True:
            # 抓帧是阻塞的 cap.read()，丢到线程里跑，别卡事件循环。没选/抓不到就跳过这帧（不发假图）。
            jpg = await asyncio.to_thread(world.cam.snapshot, "jpeg")
            if jpg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(1 / STREAM_FPS)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/cameras")    # 枚举可选摄像头（给下拉框；不打开任何设备）
def cameras() -> dict:
    return {"cameras": world.cam.cameras(), "selected": world.cam.status()["selected"]}


@app.get("/modes")      # 当前选中摄像头真支持、本世界能解码的分辨率档（给分辨率下拉框）
def modes() -> dict:
    return world.cam.modes()


class SelectIn(BaseModel):
    id: int


@app.post("/select")    # 人在下拉框选了哪个 → 世界这才连接并打开它、开始出流
def select(inp: SelectIn) -> dict:
    return world.cam.select(inp.id)


class ResolutionIn(BaseModel):
    width: int
    height: int


@app.post("/resolution")    # 人在世界页选了别的分辨率 → 重开当前摄像头并应用（只接受真支持的档）
def resolution(inp: ResolutionIn) -> dict:
    return world.cam.set_resolution(inp.width, inp.height)


@app.post("/release")   # 松开当前摄像头（回到"未选择"）
def release() -> dict:
    return world.cam.release()


@app.get("/status")
def status() -> dict:
    return world.cam.status()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(os.path.join(_HERE, "web", "index.html"))
