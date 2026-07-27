"""Text a **person** reads. Localised, unlike the prompts.

Almost everything that used to live here moved to `prompts.py`. The line between the two
files is **who reads it**, and it is worth stating because it is easy to get wrong:

  - A **model** reads it → `prompts.py`, English, one version. A prompt is a functional
    input; two versions means two products that drift, and every adjustment has to be
    re-validated in both.
  - A **person** reads it → here, and it gets localised properly.

The tool *results* went to `prompts.py` even though a human sees them in the session log,
because their primary consumer is the model: `add_note` returning "noted as entry 3" enters
the conversation as a tool message and the model acts on it. Being visible to a human is
not the same as being addressed to one.

What is left is genuinely addressed to the user: the three ways a turn can be cut short.

人读的文字。和提示词不同，它要本地化。

原先住在这里的东西几乎全搬去了 `prompts.py`。两个文件之间的界线是**谁读它**——值得写明，因为很容易
划错：

  - **模型**读的 → `prompts.py`，英文，一个版本。提示词是功能输入；两个版本等于两个会各自漂移的
    产品，而且每次调整都得在两种语言上重新验证。
  - **人**读的 → 留在这里，好好做本地化。

那些**工具回执**去了 `prompts.py`，尽管人在会话流水里也看得到——因为它们的主要消费者是模型：
`add_note` 返回的"已记下第 3 条"是以 tool 消息进对话的，模型据它行动。**"人看得到"和"是说给人听的"
不是一回事。**

留下来的这些是真正说给用户听的：一轮被提前收尾的三种情形。
"""
from __future__ import annotations

# ---- The three ways a turn ends early (v0.9) --------------------------------------------
# All three are a **pause you can resume**, not a terminal state: the core task stays
# registered and a single "continue" from the user picks it up again.
#
# They are worded separately on purpose. **The reason for stopping differs, so what the user
# should do next differs too**: too many steps or too much time suggests it may be stuck
# (perhaps rephrase), whereas an interrupt was purely the user's own decision and must not
# be described as "I got stuck".
#
# 三种情形都是「可续的停顿」而非终态：核心任务留在册，用户说一句「继续」就接着来。
#
# 之所以分开写，是因为**停下的原因不一样，用户下一步该做的事也不一样**：转太多步/跑太久说明可能卡住了
# （要不要换个说法），而主动叫停纯粹是用户自己的决定，不该被说成"我卡住了"。
MAX_STEPS_REPLY = "（这件事我连着做了不少步还没收尾，先停一下——你说「继续」我就接着来。）"
TIME_BUDGET_REPLY = "（这一轮跑的时间到上限了，先停一下——你说「继续」我就接着来。）"
INTERRUPTED_REPLY = "（好，停下了。你说「继续」我就接着刚才的做。）"

# Reason code (the orchestrator's internal steps/time/interrupt) → what the user is told.
# 停下原因 → 说法。键是编排器内部的原因码。
STOP_REPLIES = {
    "steps": MAX_STEPS_REPLY,
    "time": TIME_BUDGET_REPLY,
    "interrupt": INTERRUPTED_REPLY,
}
