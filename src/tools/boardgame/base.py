"""棋种工具适配器（BoardGameAdapter）统一接口 + 注册表。

「通用对弈树 + 可插拔棋种工具」：对弈行为树对所有棋通用，棋种差异全封装在一套工具适配器里——
每种棋实现这套接口（看盘 read_board / 算子 engine_move / 规则判断 …），开局选哪种就注入哪个，
行为树/skill 一行不改。这是 Strategy/Adapter 模式：通用树依赖抽象接口，运行时注入具体棋种。

下面协议里的 `state` 参数 = "一局游戏的状态对象"（象棋里=一个 python-chess Board）：对弈树黑板把它当
**ANIMA 的 belief（信念局面）** 持有（黑板字段名就叫 `belief`），每拍用视觉(read_board)校准、用 diff_move
认出对手走子来推进。世界才是唯一真值，belief 只是 ANIMA 的期望。
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class BoardGameAdapter(Protocol):
    id: str
    name: str

    def new_state(self) -> Any: ...
    # 视觉：一帧画面 → 棋子摆放（与 placement_of 同格式，用于轮次判断/校准）
    def read_board(self, image_png: bytes) -> dict: ...
    # 带置信度的视觉：→ (摆放, 看不清的格子集合)。对弈树据此判"看清/看不清"三态。
    def read_board_detailed(self, image_png: bytes) -> tuple[dict, set]: ...
    def placement_of(self, state: Any) -> dict: ...
    # 在 state 的合法着法里，找出"使摆放变成 observed"的那一手（=对手走的）；没变→None；对不上→None
    def diff_move(self, state: Any, observed: dict) -> Optional[Any]: ...
    def apply(self, state: Any, move: Any) -> None: ...        # 就地把一手走到 state 上
    def engine_move(self, state: Any) -> Optional[Any]: ...     # 引擎给这一手（天生合法）
    def is_terminal(self, state: Any) -> dict: ...              # {over, winner, reason}
    def my_turn(self, state: Any, my_side: str) -> bool: ...     # state 轮到 my_side 了吗
    def side_to_move(self, state: Any) -> str: ...              # "white"/"black"——替对弈树黑板算 turn，避免它直接碰棋规则
    def to_command(self, state: Any, move: Any) -> dict: ...     # move → {from,to,piece,promotion}
    def move_uci(self, move: Any) -> str: ...                    # 给日志/状态用
    def describe(self, state: Any, move: Any) -> str: ...        # 可读着法名（给解说）
    def evaluate(self, state: Any) -> int: ...                  # 我方视角形势评分(厘兵)，给认输/求和判断
    def should_resign(self, state: Any, my_side: str) -> bool: ...  # 这一拍该不该认（棋种相关；树再确认连续够多拍）


# ---- 注册表（进程内 dict；轻量，不照抄远程 WorldRegistry）----
_ADAPTERS: dict[str, BoardGameAdapter] = {}


def register_adapter(adapter: BoardGameAdapter) -> None:
    _ADAPTERS[adapter.id] = adapter


def get_adapter(adapter_id: str) -> Optional[BoardGameAdapter]:
    return _ADAPTERS.get(adapter_id)


def list_adapters() -> list[str]:
    return list(_ADAPTERS)
