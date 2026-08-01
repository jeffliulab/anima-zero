"""The example world — ANIMA's talker/listener, and the template to copy from.

ROS ships talker/listener not to prove ROS is useful, but to prove the pipes are alive:
a node starts, a topic connects, a message really crosses. This world is the same thing
for AWI. `anima demo` starts it for you; you can also run it as a standalone program:

    python -m anima.examples.minimal_world --port 8090

and then point the brain at it with `anima world add example http://localhost:8090`.

## What it is

A dot on a corridor of eight cells, seen from one camera. `step` moves the dot one cell
left or right; `look` describes what the camera sees without changing anything; the walls
at both ends refuse honestly. Its whole physics is one integer.

## ⛔ Its relationship with tests/test_awi_minimal_world.py — the two are NOT one file

The test is an independent validator: it is handwritten from docs/awi-spec-v1.md on
purpose, with protocol strings as literals, so that "the spec alone is enough to
implement" stays proven. This file is the opposite kind of thing: a teaching template
that users are meant to copy and evolve. **Do not "deduplicate" them into one
implementation** — the day they share code, the test only proves that the example agrees
with itself. (Precedent: the brain's chess advisor and the world's chess opponent share
zero code on purpose.) Each drift is fine; the conformance checker is the referee
between them.

## Reading it as a template

Every piece is annotated with the AWI spec section it implements. The four channels are:
tools (§3.1), observation (§3.2), guidance (§3.3), health (§4.1) — plus one out-of-band
endpoint, /status, which shows the person (never the brain) the god's-eye truth.

示例世界——ANIMA 的 talker/listener，也是给人抄的模板。

ROS 自带 talker/listener 不是为了证明 ROS 有用，而是为了证明**管道是活的**：节点起得来、
话题连得上、消息真的从一端到了另一端。这个世界之于 AWI 就是同一件事。`anima demo` 会替你
起它；你也可以把它当独立程序跑（命令见上），再用 `anima world add` 指过去。

与 tests/test_awi_minimal_world.py 的关系：两者**有意各自独立**——测试是规范的独立验证器
（字面量写死），本文件是教学模板。**禁止把两者去重合并**，它们之间的裁判是 conformance
checker，不是共享代码。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import socket
import threading
import time

import httpx
import mcp.types as mt
import uvicorn
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from PIL import Image, ImageDraw
from pydantic import AnyUrl

# ---- The world's own constants (domain definitions, not tunables) -------------------
# 域常量：这个世界的"物理定律"本身，集中在一处并写明含义。
STRIP_CELLS = 8                     # the corridor is eight cells long
CELL_PX = 8                         # each cell renders as 8×8 pixels
CAMERA_NAME = "front"               # the one and only camera
BACKGROUND_RGB = (16, 16, 16)
DOT_RGB = (240, 240, 240)
DEFAULT_PORT = 8090                 # standalone default; away from every port the repo's
                                    # real worlds use (8102–8112), so both can run at once

STARTUP_TIMEOUT_S = 10.0            # how long serve_in_thread waits for /health
STARTUP_POLL_S = 0.05

GUIDANCE = (
    "You are a dot on a corridor of eight cells, seen from one camera named 'front'. "
    "The lit cell in the picture is you. `look` tells you in words what the camera "
    "shows and changes nothing; `step` moves you one cell left or right, and at either "
    "end it refuses and says so. There is nothing else here — no other objects, no "
    "other tools, nothing to find. This world exists to prove the wires are connected."
)

LOOK_DESCRIPTION = (
    "Describe in words what the camera shows right now: which cell is lit, counting "
    "from the left. Changes nothing. Call it whenever you are unsure where you are — "
    "it is your eyes, and it is always safe."
)

STEP_DESCRIPTION = (
    "Move one cell along the corridor. Pass direction='left' or direction='right'. "
    "Call it when the picture shows the dot is not where you want it. Do not call it "
    "at the end of the corridor: it will refuse, and the refusal is reported as a "
    "failure rather than silently doing nothing."
)

STEP_SCHEMA = {
    "type": "object",
    "properties": {"direction": {"type": "string", "enum": ["left", "right"]}},
    "required": ["direction"],
}


# ---------------------------------------------------------------- the world itself ----

class CorridorWorld:
    """A dot on a corridor. Its entire physics is this `x`. / 全部物理就是这个 `x`。"""

    def __init__(self) -> None:
        self.x = STRIP_CELLS // 2

    def step(self, direction: str) -> tuple[bool, str]:
        delta = {"left": -1, "right": 1}.get(direction)
        if delta is None:
            return False, f"unknown direction {direction!r}; use 'left' or 'right'"
        nxt = self.x + delta
        if not 0 <= nxt < STRIP_CELLS:
            # §3.1: failures are reported honestly. Blocked means blocked — never
            # pretend nothing happened. / 失败如实报：挡住了就说挡住了。
            return False, "there is a wall that way; nothing moved"
        self.x = nxt
        return True, f"moved {direction}"

    def look(self) -> str:
        """The camera's picture, in words — the text brain's eyes.

        This is a caption of perception, not a leak of ground truth: a vision brain
        would read the same fact off the PNG. The world's god's-eye coordinate is still
        nowhere in the structured state (see observe()).
        """
        cells = ["■" if i == self.x else "□" for i in range(STRIP_CELLS)]
        return (f"Left to right: {' '.join(cells)} — the lit cell is number "
                f"{self.x + 1} of {STRIP_CELLS}, counting from the left. You are the lit cell.")

    def observe(self) -> tuple[dict, bytes]:
        """§3.2: state first, then the picture.

        ⛔ No `x` in the state. "Which cell I am actually on" is god's-eye truth — a real
        robot carries no such sensor. What it carries is a camera (the PNG) and a bump
        reading (at_wall), so those are all it gets.
        """
        state = {
            "cameras": [CAMERA_NAME],                    # name order = blob order below
            "at_wall": self.x in (0, STRIP_CELLS - 1),   # a real sensor: am I touching a wall
        }
        return state, self._render()

    def _render(self) -> bytes:
        """A real render, really PNG-encoded. A picture in the observation is exactly
        what separates AWI from an ordinary MCP server — faking it (a placeholder
        string, a hard-coded base64) would leave the channel unproven."""
        img = Image.new("RGB", (STRIP_CELLS * CELL_PX, CELL_PX), BACKGROUND_RGB)
        x0 = self.x * CELL_PX
        ImageDraw.Draw(img).rectangle([x0, 0, x0 + CELL_PX - 1, CELL_PX - 1], fill=DOT_RGB)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# ------------------------------------------------- wiring it to the four AWI channels ----

def build_app(world: CorridorWorld) -> FastAPI:
    """Mount the world on AWI, following docs/awi-spec-v1.md: four channels + one
    out-of-band endpoint for the person watching."""
    srv = Server("corridor-example")

    @srv.list_tools()                                                     # §3.1
    async def _list_tools() -> list[mt.Tool]:
        return [
            # `look` mutates nothing and says so — readOnlyHint=True is what lets a
            # cautious brain (or the mock demo brain) call it without judgement.
            mt.Tool(name="look", description=LOOK_DESCRIPTION,
                    inputSchema={"type": "object", "properties": {}},
                    annotations=mt.ToolAnnotations(readOnlyHint=True)),
            # `step` changes the world, so it explicitly declares False — declared
            # False is not the same as undeclared.
            mt.Tool(name="step", description=STEP_DESCRIPTION, inputSchema=STEP_SCHEMA,
                    annotations=mt.ToolAnnotations(readOnlyHint=False)),
        ]

    @srv.call_tool()
    async def _call_tool(name: str, arguments: dict) -> mt.CallToolResult:
        if name == "look":
            return mt.CallToolResult(content=[mt.TextContent(type="text", text=world.look())])
        if name == "step":
            ok, message = world.step((arguments or {}).get("direction", ""))
            return mt.CallToolResult(content=[mt.TextContent(type="text", text=message)],
                                     isError=not ok)                      # §3.1
        return mt.CallToolResult(content=[mt.TextContent(type="text",
                                                         text=f"no such tool: {name!r}")],
                                 isError=True)

    @srv.list_resources()                                                 # §3.2
    async def _list_resources() -> list[mt.Resource]:
        # Only this one. anima://config (§3.4) is optional, and this world has nothing
        # to configure — so the channel does not exist, rather than existing empty.
        return [mt.Resource(uri=AnyUrl("anima://observation"), name="observation",
                            description="what the robot senses right now",
                            mimeType="application/json")]

    @srv.read_resource()
    async def _read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        state, png = world.observe()
        # The order is the contract: the state's JSON text first, then the image/png
        # blobs in the same order as state.cameras.
        return [ReadResourceContents(content=json.dumps(state), mime_type="application/json"),
                ReadResourceContents(content=png, mime_type="image/png")]

    @srv.list_prompts()                                                   # §3.3
    async def _list_prompts() -> list[mt.Prompt]:
        return [mt.Prompt(name="guidance", description="what this world is")]

    @srv.get_prompt()
    async def _get_prompt(name: str, arguments: dict | None) -> mt.GetPromptResult:
        return mt.GetPromptResult(messages=[mt.PromptMessage(
            role="user", content=mt.TextContent(type="text", text=GUIDANCE))])

    # json_response=False is the one the spec calls out by name: in JSON mode the SDK
    # drops notifications/progress. This world has no long actions and sends no
    # progress; it is written by the book anyway, because this file is meant to be
    # copied as the minimal implementation.
    manager = StreamableHTTPSessionManager(app=srv, json_response=False, stateless=True)

    async def mcp_asgi(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", mcp_asgi)                                           # §2

    @app.get("/health")                                                   # §4.1
    def health() -> dict:
        return {"ok": True}

    @app.get("/status")
    def status() -> dict:
        # The out-of-band line: for the person watching, NEVER for the brain. This is
        # where the god's-eye truth lives — here it is trivial (one integer), but in a
        # navigation world this is "which room you are actually in", and the rule is
        # the same: the moment it enters perception, the ability the world exists to
        # test has been given away for free.
        return {"dot_cell": world.x + 1, "cells": STRIP_CELLS,
                "note": "for humans only — the brain never sees this"}

    return app


# --------------------------------------------------------------- ways to run it ----

@contextlib.contextmanager
def serve_in_thread(port: int = 0):
    """Serve the world on a background thread and yield its base URL.

    `port=0` asks the OS for a free one: the socket is bound first and handed to
    uvicorn as-is, so there is no "someone grabbed the port in between" window.
    `anima demo` uses this; tests may too.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", port))
    sock.listen()
    actual_port = sock.getsockname()[1]

    server = uvicorn.Server(uvicorn.Config(build_app(CorridorWorld()), host="127.0.0.1",
                                           port=actual_port, log_level="warning"))
    crash: list[BaseException] = []

    def _run() -> None:
        try:
            server.run(sockets=[sock])
        except BaseException as e:      # caught so it can be *said*, see the wait loop
            crash.append(e)

    thread = threading.Thread(target=_run, name="corridor-example-world", daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{actual_port}"
    deadline, last = time.monotonic() + STARTUP_TIMEOUT_S, None
    while time.monotonic() < deadline:
        if crash:
            raise RuntimeError(f"the example world crashed on startup: {crash[0]!r}")
        try:
            if httpx.get(base + "/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError as e:
            last = e
        time.sleep(STARTUP_POLL_S)
    else:
        raise RuntimeError(f"the example world did not answer /health within "
                           f"{STARTUP_TIMEOUT_S:g}s (last: {last!r})")
    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)        # daemon thread: worst case it cannot hang anyone


def main(argv: list[str] | None = None) -> int:
    """Standalone mode: a world is a separate program, and this one runs like one."""
    ap = argparse.ArgumentParser(prog="python -m anima.examples.minimal_world",
                                 description="The corridor example world, as a server.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help=f"default {DEFAULT_PORT}")
    args = ap.parse_args(argv)
    # flush=True：stdout 不是终端时（脚本里、Docker 里、`> log` 重定向）Python 会全缓冲，
    # 这两行会一直卡在缓冲区里不出来，世界看起来像启动挂住了。
    print(f"corridor example world on http://127.0.0.1:{args.port}  "
          f"(god's-eye for you only: http://127.0.0.1:{args.port}/status)", flush=True)
    print(f"point the brain at it with:  anima world add example "
          f"http://localhost:{args.port}", flush=True)
    uvicorn.run(build_app(CorridorWorld()), host="127.0.0.1", port=args.port,
                log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
