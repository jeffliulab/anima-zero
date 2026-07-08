"""mcp_bridge.run_alive 的「生命迹象」语义单测（v0.5 wave 0）。

这是 MCP 规范「收到 progress 应重置超时（SHOULD）+ 总上限」在本仓的落地——四条语义各一测：
失联判死 / 有进度续命 / 硬上限压过进度 / 上层取消及时生效。全部用亚秒级假负载，不碰网络。
"""
from __future__ import annotations

import asyncio
import time

import pytest

from anima.clients.mcp_bridge import Beat, CallAborted, HardCapTimeout, LivenessTimeout, run_alive

# 亚秒级测试节奏（监督器巡检步长是 config.BRIDGE_WATCHDOG_POLL_S=0.25s，参数都取它的量级）
QUIET_S = 1.2        # "闷头不吭声"的假负载时长
LIVENESS_S = 0.6     # 测试用失联阈
HARD_CAP_S = 5.0     # 测试用宽裕总上限
TOUCH_EVERY_S = 0.2  # 心跳间隔（< LIVENESS_S，模拟世界持续报进度）


async def _quiet(seconds: float) -> str:
    await asyncio.sleep(seconds)
    return "done"


async def _beating(beat: Beat, seconds: float) -> str:
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        await asyncio.sleep(TOUCH_EVERY_S)
        beat.touch()
    return "done"


def test_no_progress_hits_liveness_timeout():
    """没有任何生命迹象 → 到失联阈就判死，不傻等到总上限。"""
    t0 = time.monotonic()
    with pytest.raises(LivenessTimeout):
        run_alive(_quiet(QUIET_S), beat=Beat(), liveness_s=LIVENESS_S, hard_cap_s=HARD_CAP_S)
    assert time.monotonic() - t0 < QUIET_S, "应在失联阈附近放弃，而不是等假负载做完"


def test_progress_resets_liveness():
    """持续报进度 → 即使总时长远超失联阈也不判死（这就是长物理动作能活下来的机制）。"""
    beat = Beat()
    assert run_alive(_beating(beat, QUIET_S), beat=beat,
                     liveness_s=LIVENESS_S, hard_cap_s=HARD_CAP_S) == "done"


def test_hard_cap_beats_progress():
    """有进度也不无限等：超总上限就放弃（防世界报着进度却永远干不完）。"""
    beat = Beat()
    with pytest.raises(HardCapTimeout):
        run_alive(_beating(beat, QUIET_S * 3), beat=beat,
                  liveness_s=LIVENESS_S, hard_cap_s=QUIET_S)


def test_should_abort_cancels_promptly():
    """上层取消 → 一个巡检步长量级内放弃等待（对弈换局/用户喊停靠这条保住响应）。"""
    t0 = time.monotonic()
    with pytest.raises(CallAborted):
        run_alive(_quiet(QUIET_S * 3), beat=Beat(), liveness_s=HARD_CAP_S, hard_cap_s=HARD_CAP_S,
                  should_abort=lambda: True)
    assert time.monotonic() - t0 < 1.5
