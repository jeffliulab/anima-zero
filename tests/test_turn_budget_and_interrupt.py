"""v0.9 长回合的两道新闸：**墙钟预算**与**用户叫停**。

为什么必须有这张网（CLAUDE.md §2.6：动 orchestrator 前先有测试网）：
v0.9 把单轮步数从 8 放开到 60，让"找厨房"这种长任务能在一个回合里跑完。放开步数的前提是
另外两道闸真的管用——**跑太久要能自己停、用户点停止要真的停**。这两条要是坏了，
v0.7 那个"45-90 分钟不可中断"的废案就会原地复活。

三条契约：
1. 墙钟到顶 → 走 overflow 说时长到了（不是步数那句、不是报错），核心任务留在册；
2. 用户叫停 → 当前步做完就收尾，说的是"停下了"，且旗标被消费（不殃及下一轮）；
3. 叫停在**流式**路径同样成立（网页走的是流），且动作等待期间世界客户端能收到中止信号。

用假 LLM/世界，确定性、不联网、不睡真时间（墙钟用 deadline 直接过期来构造）。
"""
from __future__ import annotations

from anima import messages
from anima.core import interrupt
from anima.core.awi import ActionResult, Capabilities, Observation, ToolSpec
from anima.core.orchestrator import Orchestrator
from anima.clients.registry import WorldRegistry
from anima.llm import LLMReply, ToolCall
from anima.session import SessionStore


class _World:
    """假世界：一个只读 ping 工具；记下每次 invoke 收到的中止回调，供契约 3 检查。"""
    name = "w"
    base = "fake://w"

    def __init__(self):
        self._tools = [ToolSpec("ping", "原子能力", {}, "read")]
        self.n_perceive = 0
        self.abort_probes: list[bool] = []   # 每次动作时问一次"现在被叫停了吗"

    def capabilities(self):
        return Capabilities(self.name, "t", self._tools)

    def perceive(self):
        self.n_perceive += 1
        return Observation(image_png=None, state={})

    def invoke(self, name, *, _on_progress=None, _should_abort=None, **a):
        # 真实的 world_client 会在等待期间反复问它；这里问一次就够证明"信号确实传到了世界客户端"
        self.abort_probes.append(bool(_should_abort and _should_abort()))
        return ActionResult(True, f"did {name}")


class _LoopLLM:
    """假 LLM：永远要求调工具（自己绝不收尾）——这样收尾必然出自某道闸，测的就是闸。

    `on_call` 用来模拟"回合跑到一半时用户点了停止"：真实的叫停总是发生在**回合进行中**
    （网页那个停止按钮只在生成期间才出现），所以测试也必须在回合内触发，不能在开跑前置位。
    """
    vision = False
    model = "fake"

    def __init__(self, on_call=None):
        self.n = 0
        self._on_call = on_call

    def chat(self, system, history, tools, image):
        self.n += 1
        if self._on_call:
            self._on_call(self.n)
        return LLMReply(tool_calls=[ToolCall(str(self.n), "ping", {})])


def _orch(tmp_path, world):
    reg = WorldRegistry()
    reg._worlds[world.name] = world
    store = SessionStore(root=str(tmp_path))
    orch = Orchestrator(reg, store)
    session, _ = store.new(world.name, "fake")
    return orch, session


# ---------------------------------------------------------------- 契约 1：墙钟闸
def test_time_budget_stops_turn_with_its_own_wording(tmp_path):
    """跑太久 → 礼貌停顿（说的是"时间到上限"而不是"步数太多"），且是可续的。

    步数给足（远大于会转的轮数），墙钟给 0——第一步做完就该到点收尾。
    这样能证明**是墙钟这道闸拦下的**，不是步数顺带拦的。
    """
    world = _World()
    orch, session = _orch(tmp_path, world)
    out = orch.handle(session, "一直走", _LoopLLM(), max_steps=999, time_budget_s=0)

    assert out["reply"] == messages.TIME_BUDGET_REPLY, "墙钟到顶要说时长的话，别甩步数那句"
    assert out["reply"] != messages.MAX_STEPS_REPLY
    assert world.n_perceive == 1, "第一步做完就该收尾（步数没到，是墙钟拦的）"
    # 可续：收尾语落进了会话记录（网页重绘这一轮时要能看见，不能凭空消失）
    msgs = orch.store.get(session.id).messages
    assert any(m.get("role") == "assistant" and m.get("text") == messages.TIME_BUDGET_REPLY
               for m in msgs), "收尾语必须落库，否则网页重绘后这句话会消失"


# ---------------------------------------------------------------- 契约 2：用户叫停
def test_interrupt_stops_turn_and_is_consumed(tmp_path):
    """用户在回合跑到一半时点停止 → 当前步做完就收尾；旗标被消费，下一轮不受影响。"""
    world = _World()
    orch, session = _orch(tmp_path, world)
    # 第一次想事情的时候按下停止（= 用户看着它开始动手，然后点了停）
    llm = _LoopLLM(on_call=lambda n: interrupt.request(session.id) if n == 1 else None)

    out = orch.handle(session, "一直走", llm, max_steps=50, time_budget_s=999)
    assert out["reply"] == messages.INTERRUPTED_REPLY, "主动叫停别说成「我卡住了」"
    assert not interrupt.is_set(session.id), "叫停是一次性的：收尾时消费掉，不殃及下一句"
    assert world.abort_probes == [True], "动作等待期间世界客户端要收得到中止信号（点停不用干等这步走完）"

    # 下一轮不受影响：LLM 一出文字就正常收尾（证明旗标真的清了）
    class _Done:
        vision, model = False, "fake"

        def chat(self, *a):
            return LLMReply(text="好的")

    assert orch.handle(session, "继续", _Done())["reply"] == "好的"


def test_stale_interrupt_does_not_kill_next_turn(tmp_path):
    """竞态兜底：点停止时那一轮其实已经自己结束了 → 旗标不该拖累用户接着说的下一句。"""
    world = _World()
    orch, session = _orch(tmp_path, world)
    interrupt.request(session.id)          # 没有任何一轮在跑时按下停止

    class _Done:
        vision, model = False, "fake"

        def chat(self, *a):
            return LLMReply(text="你好")

    assert orch.handle(session, "你好", _Done())["reply"] == "你好", "每轮开始先清旗标"


# ---------------------------------------------------------------- 契约 3：流式路径
def test_interrupt_in_stream_path(tmp_path):
    """网页走的是流：叫停在流里也要正常收尾（reply 停顿语 + done），并带上停下的原因。"""
    world = _World()
    orch, session = _orch(tmp_path, world)
    llm = _LoopLLM(on_call=lambda n: interrupt.request(session.id) if n == 1 else None)

    evs = list(orch.handle_stream(session, "一直走", llm, max_steps=50, time_budget_s=999))
    replies = [e for e in evs if e["type"] == "reply"]
    assert replies and replies[-1]["text"] == messages.INTERRUPTED_REPLY
    assert replies[-1].get("stop_reason") == "interrupt", "前端要据此区分「停下了」和「我卡住了」"
    assert evs[-1]["type"] == "done", "流以 done 正常收尾（不是异常）"
