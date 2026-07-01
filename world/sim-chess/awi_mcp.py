"""AWI-over-MCP 适配器（世界侧，自包含，仅依赖 mcp）。

把一个实现 `capabilities()/observe()/invoke()` 的世界对象，暴露成标准 **MCP server**：
  - **tools**    ← `world.capabilities()["tools"]`（含 JSON schema；kind∈{read,judge} → readOnlyHint=真）
  - **resource** ← `anima://observation`：读它返回 state(json text) + 画面(image/png blob)
  - **prompt**   ← `guidance`：世界说明书（世界作者写的一段自我介绍）

用法（世界的 FastAPI server.py）：
    from awi_mcp import build_awi_mcp
    mcp_asgi, mcp_lifespan = build_awi_mcp(world, guidance=GUIDANCE, server_name="camera")
    app = FastAPI(title="camera world", lifespan=mcp_lifespan)
    app.mount("/mcp", mcp_asgi)
    # 其余 /stream、/、控制端点照旧——它们是带外的人类页，不进 MCP。

⚠️ 这份文件在每个世界目录各存一份副本（世界是独立进程/各自 venv，不共享 import）。改协议时四处同步。
"""
from __future__ import annotations

import contextlib
import json

import mcp.types as t
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

NON_MUTATING = {"read", "judge"}          # 非「改世界」的能力
OBSERVATION_URI = "anima://observation"   # 感知资源 URI（大脑侧 world_client.py 用同一串）
GUIDANCE_PROMPT = "guidance"              # 说明书提示词名


def build_awi_mcp(world=None, *, guidance: str = "", server_name: str = "world",
                  caps_fn=None, observe_fn=None, invoke_fn=None):
    """返回 (asgi_handler, lifespan)：挂到世界 FastAPI 的 /mcp，并用作 app 的 lifespan。

    默认从 `world` 取 capabilities()/observe()/invoke()；若世界的动作方法名不同（如 sim-desk 是 step），
    传 `invoke_fn=world.step` 覆盖即可（observe_fn/caps_fn 同理）。
    """
    _caps = caps_fn or world.capabilities        # () -> {"tools":[...], ...}
    _observe = observe_fn or world.observe        # () -> (state, image_png|None)
    _invoke = invoke_fn or world.invoke           # (name, **args) -> {"ok","message","data"}
    srv = Server(server_name)

    @srv.list_tools()
    async def _list_tools():
        caps = _caps()
        out = []
        for td in caps.get("tools", []):
            kind = td.get("kind", "tool")
            out.append(t.Tool(
                name=td["name"],
                description=td.get("description", ""),
                inputSchema=td.get("parameters") or {"type": "object", "properties": {}},
                annotations=t.ToolAnnotations(readOnlyHint=(kind in NON_MUTATING)),
            ))
        return out

    @srv.call_tool()
    async def _call_tool(name, arguments):
        res = _invoke(name, **(arguments or {}))
        if not isinstance(res, dict):
            res = {"ok": True, "message": str(res)}
        ok = bool(res.get("ok", True))
        msg = res.get("message", "") or ("ok" if ok else "failed")
        data = res.get("data") or None
        # isError 精确表达成败（如非法着 = ok False → isError True）；data 走 structuredContent。
        return t.CallToolResult(
            content=[t.TextContent(type="text", text=msg)],
            structuredContent=data,
            isError=not ok,
        )

    @srv.list_resources()
    async def _list_resources():
        return [t.Resource(
            uri=OBSERVATION_URI, name="observation",
            description="当前画面 + 结构 state（大脑感知；绝不含世界真值）",
            mimeType="application/json",
        )]

    @srv.read_resource()
    async def _read_resource(uri):
        state, image = _observe()
        out = [ReadResourceContents(content=json.dumps(state or {}), mime_type="application/json")]
        if image:  # 没画面就不给 blob（大脑据此知道"暂时没画面"，绝不伪造一张图）
            out.append(ReadResourceContents(content=image, mime_type="image/png"))
        return out

    @srv.list_prompts()
    async def _list_prompts():
        return [t.Prompt(name=GUIDANCE_PROMPT, description="世界说明书")] if guidance else []

    @srv.get_prompt()
    async def _get_prompt(name, arguments):
        return t.GetPromptResult(
            description="世界说明书",
            messages=[t.PromptMessage(role="user", content=t.TextContent(type="text", text=guidance))],
        )

    sm = StreamableHTTPSessionManager(app=srv, json_response=True, stateless=True)

    async def asgi(scope, receive, send):
        await sm.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with sm.run():
            yield

    return asgi, lifespan
