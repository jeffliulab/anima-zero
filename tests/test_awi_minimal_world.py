"""AWI 的 talker/listener：测试自带的最小世界，跑通整条一致性管道。

ROS 的 talker/listener 不证明 ROS 好用，它证明**管道是活的**——节点起得来、话题连得上、
消息真的从一端到了另一端。这个文件是 AWI 的同一件事。

⭐ 三条设计约束，改这个文件之前先读：

1. **它不连任何具体世界。** 用户完全可以只装 anima、自己写世界，`world/` 下有什么与
   「AWI 合不合规」无关。所以靶子必须自带。（被它替换掉的旧测试起的是随 wheel 分发的
   内置 desk 世界；那个世界在 v1.1.1 删掉了，而在删掉之前，那条测试就已经把「规范对不对」
   和「我们碰巧带了哪个世界」绑在了一起。）

2. **它是照着 docs/awi-spec-v1.md 独立手写的，不是 awi_mcp.py 的又一份副本。**
   ⛔ 别为了「去重」把它换成 `from awi_mcp import build_awi_mcp`——那一换，这个测试就只能
   证明「awi_mcp 和 awi_mcp 一致」，再也证明不了「这份规范光靠文字就能实现」。
   ⛔ 同理，下面的 "anima://observation" / "guidance" / "image/png" 一律写**字面量**，
   不从 anima 侧 import 常量：import 了就是同义反复——大脑侧把 URI 改成别的字符串，
   这个测试照样绿。两边各写一份、对不上就红，才是要买的东西。
   ⛔ 也不要把本文件加进 tests/test_awi_mcp_copies.py 的 COPIES——那正好把这份独立实现
   变成又一份逐字节副本，是一个精确的反向错误。

3. **起不来 = 红，不是 skip。** 靶子就在本进程里，起不来就是真坏了。旧测试用 subprocess
   起世界、把 stderr 丢进 DEVNULL、起不来 `pytest.skip` —— CI 全程绿。⛔ 别退回那个模式。

**先别做**（每加一条「顺便也测一下」，都在把它推向「又一份副本」）：anima://config、
/streams、/status、/reset、进度上报、多相机、_progress 签名探测。

这个文件只证明「一个合规的世界会被判绿」。「一个不合规的世界会被判红」由
tests/test_conformance.py 剩下那些单元测试守着（它们直接喂坏输入给每个 _check_*）。
两边合起来才是完整的网；**任何一边被删掉，另一边都会变成一个只会报成功的检查器**。
"""
from __future__ import annotations

import base64
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

from anima import conformance
from anima.clients.mcp_bridge import run_sync, with_session

# ---- AWI v1 的协议字面量。⛔ 有意写死、有意不 import（见文件头第 2 条）。----
MCP_MOUNT = "/mcp"                          # §2
OBSERVATION_URI = "anima://observation"     # §3.2
GUIDANCE_PROMPT = "guidance"                # §3.3
PNG_MIME = "image/png"                      # §3.2
HEALTH_PATH = "/health"                     # §4.1

# ---- 这个玩具世界自己的「物理」（域常量，不是可调项）----
STRIP_CELLS = 8
CELL_PX = 8
CAMERA_NAME = "front"
BACKGROUND_RGB = (16, 16, 16)
DOT_RGB = (240, 240, 240)
TOOL_NAME = "step"
SERVER_NAME = "minimal"

# ---- 测试自己的节奏参数。放这里不放 src/config.py：那是**产品**的旋钮，
#      不该为一个测试夹具多一个用户能设的 env（先例：test_awi_mcp_offloop.py）。----
STARTUP_TIMEOUT_S = 10.0
STARTUP_POLL_S = 0.05
HEALTH_PROBE_TIMEOUT_S = 0.5
SHUTDOWN_TIMEOUT_S = 5.0
MCP_CALL_TIMEOUT_S = 30.0
SHA256_HEX_CHARS = 64        # 域常量：SHA-256 十六进制串的长度

GUIDANCE = (
    "You are a dot on a strip of eight cells, seen from one camera named 'front'. "
    "The lit cell in the picture is you. `step` moves you one cell left or right; at "
    "either end it refuses and says so. There is nothing else here — no other objects, "
    "no other tools, nothing to find. This world exists to prove the wires are connected."
)

TOOL_DESCRIPTION = (
    "Move one cell along the strip. Pass direction='left' or direction='right'. Call it "
    "when the picture shows the dot is not where you want it. Do not call it at the end "
    "of the strip: it will refuse, and the refusal is reported as a failure rather than "
    "silently doing nothing."
)

TOOL_SCHEMA = {
    "type": "object",
    "properties": {"direction": {"type": "string", "enum": ["left", "right"]}},
    "required": ["direction"],
}


# ---------------------------------------------------------------- 世界本身 ----

class MinimalWorld:
    """一条 8 格走廊上的一个点。它的全部物理就是这个 `x`。"""

    def __init__(self) -> None:
        self.x = STRIP_CELLS // 2

    def step(self, direction: str) -> tuple[bool, str]:
        delta = {"left": -1, "right": 1}.get(direction)
        if delta is None:
            return False, f"unknown direction {direction!r}; use 'left' or 'right'"
        nxt = self.x + delta
        if not 0 <= nxt < STRIP_CELLS:
            # ⛔ §3.1：失败如实报。挡住了就说挡住了，不许悄悄当成功。
            return False, "there is a wall that way; nothing moved"
        self.x = nxt
        return True, f"moved {direction}"

    def observe(self) -> tuple[dict, bytes]:
        """§3.2：state 在前，画面在后。

        ⛔ state 里**没有** x。「我实际在第几格」是上帝视角真值（§1）——真机器人身上没有
        这个传感器。看得见的是画面，摸得到的是墙，所以只给这两样。
        """
        state = {
            "cameras": [CAMERA_NAME],                    # 名字顺序 = 下面 blob 的顺序
            "at_wall": self.x in (0, STRIP_CELLS - 1),   # 真传感器读数：碰到墙了吗
        }
        return state, self._render()

    def _render(self) -> bytes:
        """真渲染、真 PNG 编码，没有任何素材文件。

        ⛔ 必须是真图。observation 带图正是 AWI 与「一个普通 MCP server」的分界；
        用占位字符串或写死的 base64 冒充，这条通道就没被测到。
        """
        img = Image.new("RGB", (STRIP_CELLS * CELL_PX, CELL_PX), BACKGROUND_RGB)
        x0 = self.x * CELL_PX
        ImageDraw.Draw(img).rectangle([x0, 0, x0 + CELL_PX - 1, CELL_PX - 1], fill=DOT_RGB)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# ---------------------------------------------------- 照规范接上 AWI 四通道 ----

def _build_app(world: MinimalWorld) -> FastAPI:
    """照着 docs/awi-spec-v1.md 把这个世界接上 AWI：四条通道 + 一个带外端点。"""
    srv = Server(SERVER_NAME)

    @srv.list_tools()                                                     # §3.1
    async def _list_tools() -> list[mt.Tool]:
        return [mt.Tool(
            name=TOOL_NAME, description=TOOL_DESCRIPTION, inputSchema=TOOL_SCHEMA,
            # 它会改世界，所以显式声明 False——声明了 False，就不是「没声明」。
            annotations=mt.ToolAnnotations(readOnlyHint=False))]

    @srv.call_tool()
    async def _call_tool(name: str, arguments: dict) -> mt.CallToolResult:
        ok, message = world.step((arguments or {}).get("direction", ""))
        return mt.CallToolResult(content=[mt.TextContent(type="text", text=message)],
                                 isError=not ok)                          # §3.1

    @srv.list_resources()                                                 # §3.2
    async def _list_resources() -> list[mt.Resource]:
        # 只有这一条。anima://config（§3.4）是可选通道，这个世界没有任何可配置项，
        # 所以整条通道不存在——而不是给一个空壳。
        return [mt.Resource(uri=AnyUrl(OBSERVATION_URI), name="observation",
                            description="what the robot senses right now",
                            mimeType="application/json")]

    @srv.read_resource()
    async def _read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        state, png = world.observe()
        # 顺序就是契约：先 state 的 JSON 文本，然后依次是 image/png blob。
        return [ReadResourceContents(content=json.dumps(state), mime_type="application/json"),
                ReadResourceContents(content=png, mime_type=PNG_MIME)]

    @srv.list_prompts()                                                   # §3.3
    async def _list_prompts() -> list[mt.Prompt]:
        return [mt.Prompt(name=GUIDANCE_PROMPT, description="what this world is")]

    @srv.get_prompt()
    async def _get_prompt(name: str, arguments: dict | None) -> mt.GetPromptResult:
        return mt.GetPromptResult(messages=[mt.PromptMessage(
            role="user", content=mt.TextContent(type="text", text=GUIDANCE))])

    # json_response=False 是规范特意点名的那条：JSON 模式下 SDK 会直接丢掉
    # notifications/progress。这个世界没有长动作、不发进度，照规范写是因为这份实现
    # 就是要能被人**照抄**的最小实现。
    manager = StreamableHTTPSessionManager(app=srv, json_response=False, stateless=True)

    async def mcp_asgi(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount(MCP_MOUNT, mcp_asgi)                                        # §2

    @app.get(HEALTH_PATH)                                                 # §4.1
    def health() -> dict:
        # /streams、/stream、/status、/reset 都是可选的，这里一个都没有：单画面世界不需要
        # /streams，没人在看它，也没有需要给人核对的真值。
        return {"ok": True}

    return app


# ------------------------------------------------------------------ 起靶子 ----

@contextlib.contextmanager
def _serve(world: MinimalWorld):
    """在本进程起一个真 uvicorn 挂上这个世界，产出它的 base URL。

    ⛔ 起不来就抛，绝不 pytest.skip：靶子就在本进程里，起不来就是真坏了，
    而一条「坏了就跳过」的测试是一条永远绿的测试。
    """
    # 先自己占住端口，再把这个 socket 原样交给 uvicorn——中间没有「端口被别人抢走」的窗口
    # （先 bind 拿号、close 掉、再让 uvicorn 重新 bind 的写法有这个竞态）。
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]

    server = uvicorn.Server(uvicorn.Config(_build_app(world), host="127.0.0.1",
                                           port=port, log_level="warning"))
    crash: list[BaseException] = []

    def _run() -> None:
        try:
            server.run(sockets=[sock])
        except BaseException as e:      # 接住是为了把它**说出来**，见下面的等待循环
            crash.append(e)

    thread = threading.Thread(target=_run, name="minimal-awi-world", daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    deadline, last = time.monotonic() + STARTUP_TIMEOUT_S, None
    while time.monotonic() < deadline:
        if crash:
            raise RuntimeError(f"the minimal world crashed on startup: {crash[0]!r}")
        try:
            if httpx.get(base + HEALTH_PATH, timeout=HEALTH_PROBE_TIMEOUT_S).status_code == 200:
                break
        except httpx.HTTPError as e:
            last = e
        time.sleep(STARTUP_POLL_S)
    else:
        raise RuntimeError(f"the minimal world did not answer {HEALTH_PATH} within "
                           f"{STARTUP_TIMEOUT_S:g}s (last: {last!r})")
    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=SHUTDOWN_TIMEOUT_S)     # daemon 线程，最坏情况也挂不住 suite


def _read_observation(base: str) -> list:
    async def op(session):
        return await session.read_resource(AnyUrl(OBSERVATION_URI))
    res = run_sync(with_session(base + MCP_MOUNT, op, MCP_CALL_TIMEOUT_S), MCP_CALL_TIMEOUT_S)
    return list(res.contents)


def _call_step(base: str, direction: str):
    async def op(session):
        return await session.call_tool(TOOL_NAME, {"direction": direction})
    return run_sync(with_session(base + MCP_MOUNT, op, MCP_CALL_TIMEOUT_S), MCP_CALL_TIMEOUT_S)


def _png_bytes(contents: list) -> bytes:
    blob = next(c for c in contents[1:] if getattr(c, "blob", None) is not None)
    assert blob.mimeType == PNG_MIME
    return base64.b64decode(blob.blob)


# -------------------------------------------------------------------- 测试 ----

def test_a_world_written_only_from_the_spec_passes_conformance():
    """照着规范文字写出来的世界，必须过一致性检查。

    过不了只有两种可能：规范写着的东西检查器没在查，或者检查器在查规范里没写的东西。
    两种都是本仓的 bug——都不该由「照文档写了个世界然后发现连不上」的人替我们发现。
    """
    with _serve(MinimalWorld()) as base:
        rep = conformance.run(base)

    assert rep.conformant, \
        f"a spec-faithful world was rejected: {[c.title for c in rep.failures]}"
    assert rep.tool_names == [TOOL_NAME]
    assert sorted(rep.state_keys) == ["at_wall", "cameras"]
    # 哈希：审批钉的就是它。断言它是一个真的 SHA-256 十六进制串，而不是「非空」——
    # `assert rep.manifest_hash` 对任何握手成功的世界都恒真，等于什么都没查。
    assert len(rep.manifest_hash) == SHA256_HEX_CHARS
    int(rep.manifest_hash, 16)      # 不是十六进制就抛，这就是断言


def test_the_image_reaching_the_brain_is_a_real_png():
    """带图的 observation 正是 AWI 与「一个普通 MCP server」的分界。

    ⛔ 一致性检查器只查 blob 自称的 mimeType，它**信这句话、不解码**。所以这里把 blob
    真的解回来：解得开、尺寸对，这条通道才算被证明是通的。一张假图（占位串、写死的
    base64）骗得过检查器，骗不过 Image.open。
    """
    with _serve(MinimalWorld()) as base:
        contents = _read_observation(base)

    state = json.loads(contents[0].text)
    blobs = [c for c in contents[1:] if getattr(c, "blob", None) is not None]
    assert len(blobs) == len(state["cameras"]), "名字顺序=blob 顺序，数量必须一致"
    with Image.open(io.BytesIO(_png_bytes(contents))) as img:
        assert img.format == "PNG"
        assert img.size == (STRIP_CELLS * CELL_PX, CELL_PX)


def test_an_action_changes_what_the_next_observation_shows():
    """talker/listener 的另一半：消息真的从一端到了另一端。

    工具调用经 MCP 进去、世界真的动了、下一次感知的**像素**真的不一样了。
    tools/call 和 resources/read 在一次往返里都被穿过。
    """
    with _serve(MinimalWorld()) as base:
        before = _read_observation(base)
        result = _call_step(base, "right")
        after = _read_observation(base)

    assert not result.isError
    assert _png_bytes(before) != _png_bytes(after), \
        "动过之后画面一模一样：要么动作没到世界，要么画面是张固定的假图"
