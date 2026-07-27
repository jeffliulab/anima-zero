"""The built-in desk world as a standalone process.

Run it the same way as any other world:

    python -m anima.worlds.desk           # or: anima demo, which starts it for you

## The four channels, and which ones the brain may see

Everything the brain gets arrives over MCP at `/mcp` — capabilities, observation, actions,
guidance. Everything else on this server is **out of band**: `/status` is the god's-eye
view, `/stream` is video for a human, `/health` is liveness. None of those reach the brain,
and that separation is the point. The moment ground truth leaks into perception, the world
stops testing anything.

内置画布世界，作为独立进程运行。

启动方式和别的世界一样：

    python -m anima.worlds.desk           # 或者 anima demo，它会替你起

## 四条通道，以及大脑能看到哪些

大脑拿到的一切都从 `/mcp` 走 MCP 进来——能力、感知、动作、说明书。这台服务器上的其它东西**全是带外**
的：`/status` 是上帝视角真值、`/stream` 是给人看的视频、`/health` 是探活。**它们一个都不进大脑**，
而这条分离正是要点所在。真值一旦漏进感知通道，这个世界就不再考察任何东西了。
"""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .awi_mcp import build_awi_mcp
from .render import render_desk
from .world import GUIDANCE, DeskWorld

DEFAULT_PORT = 8114   # 别撞 world/sim-desk 的 8100——那是独立仓里那个带人类界面的完整版
STREAM_FPS = 15

world = DeskWorld()

# Defaults to this machine only. A world drives things; leaving it open to the network by
# default would mean anyone nearby can act on it.
# 默认只对本机。世界是会**动东西**的，默认对网络敞开等于让附近任何人都能操作它。
_CORS = [o.strip() for o in os.getenv("ANIMA_CORS_ORIGINS", "http://localhost:3000").split(",")
         if o.strip()]

mcp_asgi, mcp_lifespan = build_awi_mcp(world, guidance=GUIDANCE, server_name="desk",
                                       invoke_fn=world.step)

app = FastAPI(title="anima built-in desk world", lifespan=mcp_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_CORS, allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp_asgi)      # AWI：大脑只经这里


# ---------------------------------------------------------------- out of band / 带外 ---

@app.get("/health")             # 探活。故意不记流量，否则会刷屏。
def health() -> dict:
    return {"ok": True}


@app.get("/status")             # 上帝视角真值 —— ⛔ 给人核对用，绝不进感知
def status() -> dict:
    return {"pen": list(world.pen), "drawn": len(world.canvas)}


@app.post("/reset")
def reset() -> dict:
    world.reset()
    return {"ok": True}


@app.get("/stream")             # 给人看的实时画面（MJPEG，<img> 直接嵌）
async def stream() -> StreamingResponse:
    async def gen():
        while True:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + render_desk(world.pen, world.canvas, fmt="JPEG") + b"\r\n")
            await asyncio.sleep(1 / STREAM_FPS)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


def main(argv: list[str] | None = None) -> int:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(description="ANIMA's built-in desk world")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
