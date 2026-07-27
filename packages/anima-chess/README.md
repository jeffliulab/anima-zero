# anima-chess

Chess **rules** for ANIMA — legal moves, check, checkmate, draws. Not an engine: it does
not decide which move is good, only which moves exist.

给 ANIMA 用的国际象棋**规则**——合法走法、将军、将死、和棋。它不是引擎：它不判断哪步好，
只回答有哪些步可以走。

---

## Why this exists / 为什么有这个包

ANIMA used [`python-chess`](https://github.com/niklasf/python-chess) — an excellent library,
licensed GPL-3.0. Everything else ANIMA depends on is permissive: all 69 backend packages,
the 46 in the navigation world, the Unitree robot models, the scene assets. That one
exception turned the project's licence into something that needed explaining rather than
stating. This library replaces it so ANIMA can be MIT throughout.

ANIMA 原来用 [`python-chess`](https://github.com/niklasf/python-chess)——一个非常好的库，
许可证是 GPL-3.0。而 ANIMA 依赖的其它一切都是宽松协议：后端 69 个包、导航世界的 46 个包、
宇树机器人模型、场景资产。这唯一的例外让整个项目的许可证从"一句话说清的事实"变成了"需要解释的问题"。
这个库替掉它，好让 ANIMA 从头到尾都是 MIT。

## Design in one paragraph / 一段话讲设计

A position is nine integers, not an 8×8 grid: one bitboard per piece type plus one per
colour, where bit *i* means "a piece stands on square *i*". Sliding-piece attacks come from
tables precomputed at import time and indexed by the blockers that matter, so "what does
this rook attack?" is a dictionary lookup rather than a walk. Legality is decided by
finding the pinned pieces and the checking pieces **once per position**, instead of playing
and retracting every candidate move.

一个局面是九个整数、不是 8×8 的网格：每种棋子一个位棋盘、每种颜色一个，第 *i* 位表示"第 *i* 格上
有子"。滑行子的攻击范围来自 import 时预计算好的表，按"真正起作用的阻挡子"索引，所以"这个车攻击哪些
格"是一次字典查找而不是沿线行走。合法性判定靠**每个局面算一次**被牵制的子和将军的子，
而不是把每个候选走法都试走再收回。

## Correctness / 正确性

`perft` — walk the whole move tree to a fixed depth, count the leaves — against six
positions the chess programming community has used for decades. All match the published
reference figures:

`perft`——把走法树完整走到指定深度、数叶子——用国际象棋编程界沿用了几十年的六个标准局面检验。
全部命中公开参考值：

| Position / 局面 | Depth / 深度 | Nodes / 叶子数 |
|---|---|---|
| initial / 初始局面 | 5 | 4,865,609 |
| kiwipete | 4 | 4,085,603 |
| position 3 | 5 | 674,624 |
| position 4 | 4 | 422,333 |
| position 5 | 4 | 2,103,487 |
| position 6 | 4 | 3,894,594 |

That single number is a sharp test: get castling rights, en passant, promotion, pins or
check evasion wrong by one move in one position and the count comes out different. "I
played a few games and it looked fine" cannot do that.

这一个数字是极其锐利的检验：易位权、吃过路兵、升变、牵制、应将——任何一个局面里差一步走法，
总数就对不上。"我下了几盘看着没问题"做不到这一点。

```bash
pytest                                   # depth 3, a few seconds / 跑到第 3 层，几秒
ANIMA_CHESS_PERFT_DEPTH=5 pytest         # the full sweep, minutes / 完整跑一遍，几分钟
```

## Speed / 速度

Roughly two to four times slower than `python-chess` depending on the position — it uses
magic bitboards and years of tuning. What matters is the workload this was written for:
ANIMA's advisor searching a middlegame position to depth 3 takes **1.3 s**, against the
engine's 1.5 s per-move cap. Repetition detection is O(1) here (a counter keyed by Zobrist
hash) rather than a replay of the move stack, which is why search fares better than raw
move generation would suggest.

视局面不同，比 `python-chess` 慢约二到四倍——它用的是 magic bitboard，而且打磨了很多年。真正要紧的是
本库要服务的那个负载：ANIMA 的顾问引擎搜索一个中局局面到第 3 层用 **1.3 秒**，而引擎单步上限是
1.5 秒。这里的重复局面判定是 O(1)（按 Zobrist 哈希计数），不是回放整个走子栈——这就是搜索场景比
"纯走子生成"的数字看起来要好的原因。

## API

The public names deliberately match the subset of `python-chess` that ANIMA actually used,
so switching cost one import line per file:

公开的名字**刻意**与 ANIMA 实际用到的那部分 `python-chess` API 一致，所以切换的代价是每个文件改一行
import：

```python
import anima_chess as chess          # was: import chess / 原来是 import chess

board = chess.Board()
board.push(chess.Move.from_uci("e2e4"))
print(board.legal_moves, board.is_check(), board.fen())
```

## What it does not do / 它不做的事

Chess960, PGN reading or writing, opening books, UCI engine communication, SAN parsing.
None of it was used by ANIMA, so none of it is here. If you need those, use `python-chess`
— it is a better library and this one does not try to compete with it.

Chess960、PGN 读写、开局库、UCI 引擎通信、SAN 记谱解析。ANIMA 原本就没用到，所以这里也没有。
真需要那些，请用 `python-chess`——它是更好的库，这个包不打算跟它比。

## Licence / 许可证

MIT. See [`../../LICENSE`](../../LICENSE).
