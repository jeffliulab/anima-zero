"""ANIMA —— 具身机器人的大脑:AWI(世界接口)+ 注册表 + 通用 agent loop。

公开 API。具体世界(sim-desk 等)住在 anima-zero/world/ 下,只通过 AWI(World 标准)接入。
"""
from .awi import ActionResult, Capabilities, Observation, ToolSpec, World
from .llm import LLM, LLMReply, ToolCall, make_llm
from .orchestrator import Orchestrator
from .registry import WorldRegistry

__all__ = [
    "World",
    "Observation",
    "ActionResult",
    "ToolSpec",
    "Capabilities",
    "WorldRegistry",
    "Orchestrator",
    "LLM",
    "ToolCall",
    "LLMReply",
    "make_llm",
]
