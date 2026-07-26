"""sim-house-nav 世界服务：把 HouseNavWorld 暴露成一个标准「世界」(AWI over MCP)。

AWI（脑↔世界，走 /mcp）：tools（三个导航原语）/ resources（感知=画面+朝向）/ prompts（世界说明书）。
人类页 / 控制（世界本地，不进 AWI、与大脑解耦）：/ 、/stream 、/streams 、/status 、/reset 、/config 、/health。

⚠️ /status 是**上帝视角真值**（狗在哪间屋），只给人做验收，绝不进大脑的观测。
"""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

import config as C
from awi_mcp import build_awi_mcp
from world import GUIDANCE, HouseNavWorld

world = HouseNavWorld()

mcp_asgi, mcp_lifespan = build_awi_mcp(world, guidance=GUIDANCE, server_name="sim-house-nav",
                                       config_fn=world.config)

app = FastAPI(title="sim-house-nav world", lifespan=mcp_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=C.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp_asgi)   # 大脑经此 list_tools / read_resource(感知) / call_tool / get_prompt

_HERE = os.path.dirname(os.path.abspath(__file__))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "policy_loaded": bool(world.sim.policy_path)}


# ===== 人类页 / 控制（不进 AWI）=====
@app.get("/streams")   # 有哪几路相机直播（前端据此展示；本世界就狗头一路）
def streams() -> list[dict]:
    r = world.sim.robot
    return [{"name": r["camera"], "label": f'{r["label"]}·头部前视相机', "url": "/stream"}]


@app.get("/stream")    # MJPEG 直播：人在网页上实时看到"狗眼前"的画面
async def stream() -> StreamingResponse:
    async def gen():
        while True:
            jpg = world.sim.frame_jpeg()
            if jpg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(1 / max(1, C.STREAM_FPS))

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/snapshot")  # 单帧 PNG（调试/验收用）
def snapshot() -> Response:
    png = world.sim.frame_png()
    if png is None:
        return Response(status_code=503, content=b"", media_type="image/png")
    return Response(content=png, media_type="image/png")


@app.get("/status")    # ⚠️ 上帝视角真值：狗在哪间屋。只给人验收，绝不给 ANIMA
def status() -> dict:
    return world.status()


@app.post("/reset")    # 把机器人放回出生点（人类页按钮）
def reset() -> dict:
    return world.reset()


@app.get("/config")    # 这个世界能配什么、现在是什么（和 AWI 的 anima://config 同一份内容）
def get_config() -> dict:
    return world.config()


@app.post("/config")   # 改配置（换身体）。⚠️ 带外：这是**人**的动作，不走 AWI、大脑调不到
def set_config(body: dict) -> dict:
    key = str(body.get("key", ""))
    value = str(body.get("value", ""))
    if not key or not value:
        return {"ok": False, "message": "要同时给 key 和 value，比如 {\"key\":\"body\",\"value\":\"g1\"}。"}
    return world.set_config(key, value)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(os.path.join(_HERE, "web", "index.html"))
