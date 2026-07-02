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

# ---- 观测空间（v0.5 视觉桥）：识别器"看"到的是哪种盘 ----
# 读盘接口不再假定"总能认出子型"：便宜的追踪层只认每格「空/白/黑」（OCC），
# 模板匹配/CNN 才认「具体子型」（PIECE）。适配器按当前识别器所在空间做投影（observed_of），
# diff_move 等逻辑对两种空间通用。
OCC = "occ"      # 占用+颜色：{square: 'w'|'b'}（空格不出现）
PIECE = "piece"  # 子型：{square: 'P'/'n'/...}（大写白小写黑，空格不出现）


@runtime_checkable
class BoardGameAdapter(Protocol):
    id: str
    name: str

    def new_state(self) -> Any: ...
    # 视觉：一帧画面 → 棋子摆放（与 placement_of 同格式，用于轮次判断/校准）
    def read_board(self, image_png: bytes) -> dict: ...
    # 带置信度的视觉：→ (摆放, 看不清的格子集合)。对弈树据此判"看清/看不清"三态。
    # 摆放所在的观测空间 = 适配器当前识别器的空间（OCC 或 PIECE），由 observed_of 保证两侧一致。
    def read_board_detailed(self, image_png: bytes) -> tuple[dict, set]: ...
    # 带置信度的【占用】读取（OCC 空间）：→ ({square: 'w'|'b'}, 看不清的格子集合)。
    # 任何识别器都能给（子型盘塌成占用盘即可）；追踪层识别器原生就在这个空间。
    def read_board_occupancy(self, image_png: bytes) -> tuple[dict, set]: ...
    def placement_of(self, state: Any) -> dict: ...
    # state 在【当前识别器观测空间】里的投影（PIECE→placement_of 逐字节等价；OCC→占用+颜色盘）。
    # diff_move 等"观测 vs 期望"的比较一律用它，保证两侧在同一空间。
    def observed_of(self, state: Any) -> dict: ...
    # 在 state 的合法着法里，找出"使摆放变成 observed"的那一手（=对手走的）；没变→None；对不上→None
    def diff_move(self, state: Any, observed: dict) -> Optional[Any]: ...
    def apply(self, state: Any, move: Any) -> None: ...        # 就地把一手走到 state 上
    def engine_move(self, state: Any) -> Optional[Any]: ...     # 引擎给这一手（天生合法）
    def is_terminal(self, state: Any) -> dict: ...              # {over, winner, reason}
    def my_turn(self, state: Any, my_side: str) -> bool: ...     # state 轮到 my_side 了吗
    def side_to_move(self, state: Any) -> str: ...              # "white"/"black"——替对弈树黑板算 turn，避免它直接碰棋规则
    def to_command(self, state: Any, move: Any) -> dict: ...     # move → {from,to,piece,promotion}
    # 把一手「逻辑棋」拆成「物理原语序列」，按世界支持的原语 prims（工具名集合，如 {"move","remove","place"}）决定拆多细：
    #   仅有 move（数据世界，如 sim-chess）→ [move]，吃子/易位/过路兵/升变都靠世界数据层一步吞；
    #   有 remove/place（物理世界，如 gazebo-chess）→ 真拆（吃子=remove+move、过路兵=remove被吃兵+move、
    #   易位=move王+move车、升变=move+remove+place新子）。每个原语 = {"op": "move|remove|place", ...参数}。
    #   靠「世界有哪些原语」判，不靠世界名——这是「框架不被某个世界特例污染」的关键。
    def expand_move(self, state: Any, move: Any, prims: set) -> list[dict]: ...
    # 从一帧画面构造「信念局面」（半路接手 / 开局 seed）。轮到谁走图上看不出，由调用方给（默认白先）。
    def seed_from_vision(self, image_png: bytes, side_to_move: str = "white") -> Any: ...
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
