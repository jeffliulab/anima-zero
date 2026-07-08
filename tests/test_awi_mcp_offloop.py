"""世界侧 MCP 适配器的「离环 + 进度」契约测试（v0.5 wave 0 框架修正）。

守三条契约（v0.4 的雷：长动作同步跑在事件循环上，一次 move 冻住整个世界服务器 35 秒）：
1. 慢工具执行期间，世界服务器的事件循环必须保持响应（带外 /ping 亚秒级返回）；
2. 世界声明了 keyword-only `_progress` 时，进度按 MCP `notifications/progress` 真送达客户端；
3. 没声明 `_progress` 的即时世界（sim-desk/sim-chess/camera 形态）一行不改、照常工作。

测试起一个真 uvicorn（环回随机端口）+ 真 MCP 往返，不 mock 协议层——协议层正是被测对象。
awi_mcp.py 从 world/sim-chess/ 加载（各世界这份字节一致由 test_awi_mcp_copies 守住；测的世界是下面
的 inline mock，借哪个世界的 awi_mcp 都一样——原借 gazebo-chess，它已迁去 soma-zero，改借 sim-chess）。
"""
from __future__ import annotations

import contextlib
import importlib.util
import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

from anima.clients.mcp_bridge import run_sync, with_session

ROOT = Path(__file__).resolve().parent.parent

SLOW_TOOL_TOTAL_S = 1.2     # 慢工具总时长（测试用，压缩到秒级；真世界是几十秒同一形态）
SLOW_TOOL_STAGES = 4        # 慢工具分几个阶段（每阶段报一次进度）
PING_BUDGET_S = 0.5         # 慢工具执行期间，带外路由必须多快返回
CALL_TIMEOUT_S = 30.0       # 测试里 MCP 调用的宽裕上限


def _load_awi_mcp():
    p = ROOT / "world" / "sim-chess" / "awi_mcp.py"
    spec = importlib.util.spec_from_file_location("awi_mcp_under_test", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SlowWorld:
    """声明了 `_progress` 的慢世界：干活分阶段、边干边报（gazebo-chess 的最小同构）。"""

    def capabilities(self):
        return {"tools": [{"name": "slow_op", "description": "分阶段慢活",
                           "parameters": {"type": "object", "properties": {}}, "kind": "tool"}]}

    def observe(self):
        return {}, None

    def invoke(self, name, *, _progress=None, **args):
        note = _progress or (lambda p, m="": None)
        for i in range(SLOW_TOOL_STAGES):
            note((i + 1) / (SLOW_TOOL_STAGES + 1), f"阶段 {i + 1}")
            time.sleep(SLOW_TOOL_TOTAL_S / SLOW_TOOL_STAGES)
        return {"ok": True, "message": "慢活干完了"}


class InstantWorld:
    """没声明 `_progress` 的即时世界（sim 世界形态）——契约：零改动照常工作。"""

    def capabilities(self):
        return {"tools": [{"name": "fast_op", "description": "立即返回",
                           "parameters": {"type": "object", "properties": {}}, "kind": "tool"}]}

    def observe(self):
        return {"hello": 1}, None

    def invoke(self, name, **args):
        return {"ok": True, "message": "立即完成"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _serve(world):
    """起一个真 uvicorn（环回随机端口）挂 /mcp + 带外 /ping，用完关掉。"""
    mod = _load_awi_mcp()
    asgi, lifespan = mod.build_awi_mcp(world, guidance="测试世界", server_name="test-world")
    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", asgi)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            httpx.get(base + "/ping", timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("测试世界服务器没起来")
    try:
        yield base
    finally:
        server.should_exit = True
        th.join(timeout=5)


def _call_tool(base: str, name: str, on_progress=None):
    """经大脑自己的 mcp_bridge 调一次工具（顺便覆盖桥本身），可选装进度回调。"""
    async def op(s):
        cb = None
        if on_progress is not None:
            async def cb(progress, total, message):
                on_progress((progress, total, message))
        return await s.call_tool(name, {}, progress_callback=cb)

    return run_sync(with_session(base + "/mcp", op, CALL_TIMEOUT_S), CALL_TIMEOUT_S)


def test_slow_tool_keeps_event_loop_responsive():
    """慢工具执行期间，事件循环必须活着：/ping 全程亚秒返回（v0.4 是 8/10 探测超时）。"""
    with _serve(SlowWorld()) as base:
        result: dict = {}

        def call():
            result["res"] = _call_tool(base, "slow_op")

        th = threading.Thread(target=call)
        th.start()
        time.sleep(SLOW_TOOL_TOTAL_S / SLOW_TOOL_STAGES / 2)   # 等慢活确实开跑
        pings = []
        while th.is_alive():
            t0 = time.perf_counter()
            httpx.get(base + "/ping", timeout=PING_BUDGET_S)
            pings.append(time.perf_counter() - t0)
            time.sleep(0.1)
        th.join(timeout=CALL_TIMEOUT_S)
        assert pings, "慢工具跑完前一次 ping 都没发出去——测试节奏错了"
        assert max(pings) < PING_BUDGET_S
        assert not result["res"].isError


def test_progress_reaches_brain_client():
    """世界报的进度必须真送达大脑侧客户端（≥2 条、带人话消息、比例递增）。"""
    got: list[tuple] = []
    with _serve(SlowWorld()) as base:
        res = _call_tool(base, "slow_op", on_progress=got.append)
    assert not res.isError
    assert len(got) >= 2, f"进度没送达（只收到 {len(got)} 条）——json_response 模式会丢通知，检查 awi_mcp"
    fracs = [p for p, _tot, _msg in got]
    assert fracs == sorted(fracs)
    assert any("阶段" in (msg or "") for _p, _tot, msg in got)


def test_instant_world_without_progress_param_unchanged():
    """没声明 `_progress` 的即时世界零改动：工具照常、感知照常（不会被误传参数炸掉）。"""
    with _serve(InstantWorld()) as base:
        res = _call_tool(base, "fast_op")
        assert not res.isError
        assert "立即完成" in "".join(c.text for c in res.content if getattr(c, "text", None))

        async def op(s):
            from pydantic import AnyUrl
            return await s.read_resource(AnyUrl("anima://observation"))

        rd = run_sync(with_session(base + "/mcp", op, CALL_TIMEOUT_S), CALL_TIMEOUT_S)
        assert any(getattr(c, "text", None) for c in rd.contents)
