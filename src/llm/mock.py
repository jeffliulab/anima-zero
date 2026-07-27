"""A brain that does not think — for proving the wiring works without an API key.

## Why this exists

Installing ANIMA and finding that nothing runs until you have signed up for a model
provider is a bad first five minutes, and it makes the first thing a new user sees an
error rather than the system. This brain lets the whole loop run end to end — perceive,
decide, call a tool, get a result back, reply — with no key and no network.

## What it does, exactly

Step one of a turn: if the world offers a tool the world itself declares as non-mutating,
call the first such tool with zero-valued arguments. Step two: answer in text.

**It never calls an action that changes the world.** Not because it is being clever — it
cannot tell a safe action from a dangerous one — but because something that picks blindly
has no business touching anything. If a world offers only world-changing tools, it calls
nothing and says so.

(That check reads the world's own `kind`, which a world could lie about. Here that is
acceptable: this is a fallback for a brain with no judgement, not a security control. The
control is the approval in `core/trust.py`.)

## What it is not

It does not look at the picture. It does not read what you typed. It does not choose the
tool — it takes whichever safe one happens to be first. Calling that a decision would be a
lie, and a mock that pretends to be intelligent is worse than no mock, because it makes a
broken setup look like a working one.

一个**不思考**的大脑——用来在没有 API key 的情况下证明链路是通的。

## 为什么有它

装完 ANIMA 却发现"不先去注册一个模型服务商就什么都跑不起来"，是很糟的头五分钟；而且它让新用户看到的
第一样东西是报错，不是这个系统。有了它，整条链路可以完整跑一遍——看、想、调工具、拿回结果、回话
——不需要 key，也不需要联网。

## 它到底做什么

一轮的第一步：如果世界提供了**它自己声明为不改变世界**的工具，就调其中第一个，必填参数按 schema
用零值填上。第二步：出文字收尾。

**它绝不调用会改变世界的动作。** 不是因为它聪明——它根本分不清安全和危险——而是因为**一个瞎选的
东西没资格碰任何东西**。如果一个世界只提供会改变世界的工具，它就什么都不调，并说明原因。

（这个判断读的是世界自己声明的 `kind`，而世界可以在这上面撒谎。这里可以接受：它是给一个没有判断力的
大脑兜底，不是安全控制。安全控制是 `core/trust.py` 里那道审批。）

## 它不是什么

它**不看画面**，**不读你打的字**，**也不挑工具**——它拿的就是恰好排在第一个的那个安全工具。
把这叫做"决策"是撒谎；而一个假装有智能的 mock 比没有 mock 更糟，因为它会把一个坏掉的配置显示成
正常的。
"""
from __future__ import annotations

from ..core.awi import NON_MUTATING_KINDS
from .base import LLMReply, ToolCall

# Said in every text reply. A user who wandered in from a screenshot needs to be told what
# they are looking at, in the place they are actually looking.
# 每条文字回复都带上。一个从截图里点进来的用户需要**在他真正在看的地方**被告知他看到的是什么。
DISCLAIMER = (
    # ⚠️ 措辞不能假设界面：同一段话会出现在网页里、也会出现在 `anima chat` 的终端里。
    #    说"右边的流水""上面的下拉"在终端里就是错的。
    "(This is the mock brain. It does not look at the picture, does not read what you "
    "said, and makes no judgement — it walks the chain end to end so you can watch it. "
    "For a brain that actually thinks, configure an API key and pick another one.)"
)

_ZERO = {"string": "", "number": 0, "integer": 0, "boolean": False,
         "array": [], "object": {}}


def _zero_args(schema: dict) -> dict:
    """Fill a tool's required arguments with zero-values of the right type.

    Not "sensible" values — zero-values. Guessing at plausible arguments would be the same
    lie as pretending to choose the tool.

    按 schema 的类型给必填参数填**零值**。

    不是"合理的"值，是零值。猜一组看起来像样的参数，和假装在挑工具是同一种谎。
    """
    props = (schema or {}).get("properties") or {}
    return {name: _ZERO.get((props.get(name) or {}).get("type"), "")
            for name in (schema or {}).get("required") or []}


class MockLLM:
    """Implements the LLM protocol. / 实现 LLM 协议。"""

    vision = False
    model = "mock"

    def chat(self, system: str, history: list[dict], tools: list, image_png=None) -> LLMReply:
        # "Have I already acted this turn?" is answered by looking for a tool result at the
        # end of the history — the same signal a real brain would use, so the loop is
        # exercised the way it really runs rather than by counting calls on this object
        # (which would go wrong the moment two sessions share a brain).
        # 「这一轮我动过手了吗」靠**历史末尾有没有工具结果**来判断——这和真大脑用的是同一个信号，
        # 所以链路是按它真实的样子被走一遍的；而不是在这个对象上记调用次数（两个会话共用一个大脑
        # 的那一刻就会错）。
        acted = any(m.get("role") == "tool" for m in reversed(history[-4:]))
        safe = next((t for t in tools if t.kind in NON_MUTATING_KINDS), None)

        if safe and not acted:
            return LLMReply(tool_calls=[ToolCall("mock-1", safe.name, _zero_args(safe.parameters))])

        if not tools:
            return LLMReply(text="This world offers no callable actions, so there is "
                                 "nothing to demonstrate.\n" + DISCLAIMER)
        if safe is None:
            return LLMReply(text=(
                f"All {len(tools)} of this world's actions change it, and I choose at "
                f"random — so I will call none of them. Bring a real brain; it is the "
                f"only thing entitled to decide which one to use.\n" + DISCLAIMER))
        return LLMReply(text=f"The chain works: I called `{safe.name}`, the world answered, "
                             f"and every step is in this session's trace.\n" + DISCLAIMER)
