"""回归：OpenAI 兼容层把历史拼成 messages 时，助手消息的 content 必须永远是字符串。

最毒的一种历史：ANIMA 某一回合**只调了工具、没有文字**（text=""，但带 tool_calls）。
旧写法 `it.get("text") or None` 会把这条的 content 变成 None → JSON 的 null →
qwen3-vl / gpt-5.5 直接 400（`content ... null` / `invalid message content type: <nil>`），
连带主循环崩在思考这一步、`enter_skill` 永远没机会被调 → 进不了游戏模式。content 必须给空串。
"""
from __future__ import annotations

from anima.llm.base import ToolCall
from anima.llm.openai_compat import _messages


def test_assistant_with_tool_calls_no_text_keeps_string_content():
    history = [
        {"role": "user", "text": "咱俩下盘棋，你执黑"},
        # 助手这一拍只调了 take_seat、没有文字——正是触发 null content 的那种回合
        {"role": "assistant", "text": "", "tool_calls": [ToolCall("c1", "take_seat", {"seat": "black"})]},
        {"role": "tool", "id": "c1", "content": "{\"ok\": true}"},
    ]
    msgs = _messages("你是 ANIMA", history, None)

    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert assistant_msgs, "应有一条助手消息"
    for m in assistant_msgs:
        assert m["content"] is not None, "助手 content 绝不能是 None（OpenAI 协议会 400）"
        assert isinstance(m["content"], str), "助手 content 必须是字符串（哪怕空串）"
    # 这条只调工具的回合：content="" 且 tool_calls 透传
    only_tool = assistant_msgs[0]
    assert only_tool["content"] == ""
    assert only_tool["tool_calls"][0]["function"]["name"] == "take_seat"


def test_assistant_with_text_preserved():
    history = [{"role": "assistant", "text": "我执黑就座了", "tool_calls": []}]
    msgs = _messages("sys", history, None)
    assistant = next(m for m in msgs if m["role"] == "assistant")
    assert assistant["content"] == "我执黑就座了", "有文字时原样保留"
