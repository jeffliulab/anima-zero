"""The built-in demo world: a desk, a pen, and a canvas you can draw on.

## Why a world ships inside the brain's package

Every other world in this project is a separate process in its own repository, and that
separation is the point of AWI. This one is the exception, for one reason: `pip install
anima` has to lead somewhere. A framework whose first command fails because you have not
yet found and started a world is a framework nobody evaluates.

So this is the smallest world that still exercises every channel of the protocol —
capabilities, observation, actions, guidance — and it carries no dependency the brain does
not already have. It runs as its own process like any other world; it simply happens to be
distributed in the same wheel.

It also serves as the **reference implementation** for the AWI specification: when the spec
says a world must do something, this is the code that shows what that looks like.

Note the deliberate mix of `kind`s below. `count_marks` reads and changes nothing;
the other three change the world. That distinction is what the safety gate and the mock
brain both key on, and a reference implementation that only had one kind would teach the
wrong thing.

内置的演示世界：一张桌子、一支笔、一块可以涂画的画布。

## 为什么会有一个世界住在大脑的包里

这个项目里其它每一个世界都是独立仓库里的独立进程，而这种分离正是 AWI 的意义所在。这一个是例外，
理由只有一个：**`pip install anima` 之后得有个去处**。一个"第一条命令就失败、因为你还没找到并起一个
世界"的框架，没有人会评估它。

所以这是**仍然能走通协议每一条通道**（能力、感知、动作、说明书）的最小世界，而且不引入任何大脑本来
没有的依赖。它和别的世界一样作为独立进程运行，只是恰好和大脑装在同一个 wheel 里。

它同时是 AWI 规范的**参考实现**：规范说"世界必须怎样"的时候，这份代码就是那句话长什么样。

注意下面 `kind` 的**有意混搭**：`count_marks` 只读、什么都不改；另外三个会改变世界。安全闸和 mock
大脑都是按这个区分工作的，而一个只有单一 kind 的参考实现会教错东西。
"""
from __future__ import annotations

from .render import GH, GW, render_desk

_XY = {
    "type": "object",
    "properties": {
        "x": {"type": "number", "description": "0..1, left to right"},
        "y": {"type": "number", "description": "0..1, top to bottom"},
    },
    "required": ["x", "y"],
}

_AREA = {
    "type": "object",
    "properties": {
        "x1": {"type": "number", "description": "left edge, 0..1"},
        "x2": {"type": "number", "description": "right edge, 0..1"},
        "y1": {"type": "number", "description": "top edge, 0..1"},
        "y2": {"type": "number", "description": "bottom edge, 0..1"},
    },
    "required": ["x1", "x2", "y1", "y2"],
}

# Each description says when to call it AND when not to — that is where "should I call this
# at all?" is actually decided, far more than in the brain's system prompt.
# 每条描述都写清「什么时候调 / 什么时候别调」——「到底该不该调」真正被决定的地方在这儿，
# 比在大脑的系统提示词里管用得多。
TOOLS = [
    {"name": "count_marks",
     "description": ("Report how many cells are currently filled in on the canvas. Reads "
                     "the desk and changes nothing. Safe to call at any time."),
     "parameters": {"type": "object", "properties": {}},
     # ⛔ Read-only, and it says so. The brain's safety gate treats this as a hint, never as
     # permission — see core/safety.py. / ⛔ 只读，而且它这么声明了。大脑的安全闸把这当**提示**，
     # 永远不当**许可**——见 core/safety.py。
     "kind": "read"},
    {"name": "move_pen",
     "description": ("Move the pen to (x, y) on the desk. Moves only — it leaves no mark. "
                     "Call this when the user asks to put or move the pen somewhere. To "
                     "fill an area use draw; to clear one use erase; when the user is just "
                     "greeting you or asking a question, do not call anything."),
     "parameters": _XY, "kind": "tool"},
    {"name": "draw",
     "description": ("Fill a rectangle on the canvas, given by the four edges x1, x2, y1, "
                     "y2 in 0..1. Call this only when the user asks for something to be "
                     "drawn or filled in. It does not move the pen and does not erase."),
     "parameters": _AREA, "kind": "tool"},
    {"name": "erase",
     "description": ("Clear a rectangle on the canvas, given by the four edges x1, x2, y1, "
                     "y2 in 0..1. Call this only when the user asks for something to be "
                     "erased or cleared. It does not draw and does not move the pen."),
     "parameters": _AREA, "kind": "tool"},
]

# The world's own account of itself — this is what reaches the brain as `guidance`.
#
# ⚠️ Keep it about *how to deal with me*, never about *what the answer is*. A world that
# hands over conclusions is not being helpful; it is giving away the ability it exists to
# test. (The navigation world learnt this the hard way: it used to list every room's
# furniture, and the score did not improve.)
#
# 世界对自己的说明——它会作为 `guidance` 送到大脑那里。
#
# ⚠️ 只讲**怎么跟我打交道**，绝不讲**答案是什么**。一个把结论直接交出去的世界不是在帮忙，
# 而是在白送它本该考察的那个能力。（导航世界为此付过学费：它曾把每个房间的家具逐一列出，分数并没变好。）
GUIDANCE = """\
You are looking at a desk seen from above. A pen sits on it, and part of the surface is a
canvas you can mark.

Coordinates run from 0 to 1: x from the left edge to the right, y from the top down. So
(0, 0) is the top-left corner and (1, 1) the bottom-right.

What you see in the picture is all you get — there is no separate readout of what is drawn.
Work out the state from the image, act, then look again to check what actually happened.
"""


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class DeskWorld:
    """The desk itself: it holds its own state, renders its own picture, and changes only
    through `step`. / 桌子本体：自己持有状态、自己渲染画面、只经 `step` 改变。"""

    def __init__(self) -> None:
        self.pen = [0.5, 0.5]
        self.canvas: set[tuple[int, int]] = set()

    def capabilities(self) -> dict:
        return {"name": "desk", "version": "1.0", "tools": TOOLS}

    def observe(self) -> tuple[dict, bytes]:
        """Look: structured state plus the rendered picture.

        `state` stays deliberately thin. What the canvas looks like belongs in the image —
        putting it in the state as well would let the brain skip looking, which is the one
        thing this world exists to make it do.

        看：结构化状态 + 渲染出来的画面。

        `state` **有意**保持很薄。画布长什么样属于画面；把它也塞进 state，等于让大脑可以不看图——
        而"逼它去看"正是这个世界存在的理由。
        """
        return {"pen": list(self.pen), "drawn": len(self.canvas)}, render_desk(self.pen, self.canvas)

    def _fill(self, x1: float, x2: float, y1: float, y2: float, on: bool) -> int:
        x1, x2 = sorted((_clamp(x1), _clamp(x2)))      # 反着给也接受，自动换过来
        y1, y2 = sorted((_clamp(y1), _clamp(y2)))
        cols = range(min(int(x1 * GW), GW - 1), min(int(x2 * GW), GW - 1) + 1)
        rows = range(min(int(y1 * GH), GH - 1), min(int(y2 * GH), GH - 1) + 1)
        cells = {(r, c) for r in rows for c in cols}
        if on:
            changed = cells - self.canvas
            self.canvas |= cells
        else:
            changed = cells & self.canvas
            self.canvas -= cells
        return len(changed)

    def step(self, name: str, **args) -> dict:
        """Do: run one action and report honestly what came of it.
        / 动：执行一个动作，并**如实**汇报结果。"""
        if name == "count_marks":
            return {"ok": True, "message": f"{len(self.canvas)} cells are filled in.",
                    "data": {"drawn": len(self.canvas)}}
        if name == "move_pen":
            self.pen = [_clamp(args["x"]), _clamp(args["y"])]
            return {"ok": True, "message": f"Pen moved to ({self.pen[0]:.2f}, {self.pen[1]:.2f}).",
                    "data": {"pen": list(self.pen)}}
        if name == "draw":
            n = self._fill(args["x1"], args["x2"], args["y1"], args["y2"], True)
            return {"ok": True, "message": f"Filled in {n} cells.",
                    "data": {"drawn": len(self.canvas)}}
        if name == "erase":
            n = self._fill(args["x1"], args["x2"], args["y1"], args["y2"], False)
            return {"ok": True, "message": f"Cleared {n} cells.",
                    "data": {"drawn": len(self.canvas)}}
        # Unknown action: say so plainly rather than silently doing nothing. A world that
        # quietly ignores an action teaches the brain that the action worked.
        # 未知动作：明说，而不是默默什么都不做。一个静默忽略动作的世界，会教会大脑"那个动作成功了"。
        return {"ok": False, "message": f"This desk has no action called {name!r}.", "data": {}}

    def reset(self) -> None:
        self.pen = [0.5, 0.5]
        self.canvas = set()
