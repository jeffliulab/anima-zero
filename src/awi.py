"""AWI(Anima World Interface)—— 脑 ↔ 世界 的接口标准(只定标准,不写实现)。

任何外部实体只要实现 ``World`` 协议的三个方法,就能作为一个「世界」接入 ANIMA。
这套标准借鉴 MCP / ROS:契约优先、接入时能力协商、每个能力带 JSON Schema、
感知双路(图片 + 结构状态)、传输无关。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Observation:
    """感知双路:图片喂大脑;结构状态作 ground-truth(给将来的高频环节 / 裁判)。"""

    image_png: bytes | None  # 渲染图 / 摄像头帧;某些世界可能没有图 → None
    state: dict[str, Any]  # 结构化状态,例如 {"pen": [0.5, 0.5]}


@dataclass
class ActionResult:
    """一次动作的结果。"""

    ok: bool
    message: str = ""  # 给大脑 / 用户看的自然语言结果
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    """一个 tool（世界能力）的标准声明,带 JSON Schema,大脑据此知道怎么调。

    注:「skill / 行为树」是**脑内**结构、不上 AWI 线,与这里的 tool 是两回事(别再用 kind="skill")。"""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema(object 型)
    # kind 取值:"tool"(原子)/ "judge"(裁判,确定性)/ "read"(只读感知)。
    # 其中 judge / read 属于 NON_MUTATING_KINDS:框架视为「不改世界」,动作下发时不过安全闸。
    kind: str = "tool"


# 「不改世界」的能力类别:框架对它们不走确定性安全闸(见 orchestrator)。
# 单一来源——契约和编排器都引用这里,别再各写一份字符串元组。
NON_MUTATING_KINDS: frozenset[str] = frozenset({"read", "judge"})


@dataclass
class Capabilities:
    """世界接入时的能力声明(MCP 式 capability negotiation)。"""

    name: str
    version: str
    tools: list[ToolSpec]
    # 注：「角色/席位」不另设一套声明——世界若有可担任的角色，就在 tools 里声明一个就座类工具
    #   （如 sim-chess 的 take_seat，枚举里列出可选角色），ANIMA 调它来就座；"当前谁坐哪一席" 经 perceive
    #   的 state.controllers 读。（曾经的 Seat/seats/claim 声明已删——和 take_seat 工具重复，没接线、是死的。）


@runtime_checkable
class World(Protocol):
    """★ AWI 的核心:世界标准。实现这三个方法,就能作为一个世界接入 ANIMA。"""

    def capabilities(self) -> Capabilities: ...

    def perceive(self) -> Observation: ...

    def invoke(self, name: str, **kwargs: Any) -> ActionResult: ...
