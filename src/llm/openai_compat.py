"""OpenAI 云端 + 本地 Ollama —— 都走 OpenAI 兼容接口,改 base_url 即可切换。"""
from __future__ import annotations

import base64
import json

from ..awi import ToolSpec
from .base import LLMReply, ToolCall


class OpenAICompatLLM:
    vision = True

    def __init__(self, model: str, base_url: str | None, api_key: str):
        from openai import OpenAI

        self.model = model
        # 用占位 key 也能构造客户端(没 key 时 import / 启动不报错,真正调用时才报鉴权错)
        self.client = OpenAI(base_url=base_url, api_key=api_key or "EMPTY")

    def chat(self, system, history, tools, image_png) -> LLMReply:
        # 注意:不传 max_tokens —— OpenAI 路径不需要输出上限(Anthropic 才必须);
        # 而且新模型(gpt-5.5 等)只认 max_completion_tokens,传 max_tokens 会 400。不传最稳,也不破坏 Ollama。
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=_messages(system, history, image_png),
            tools=_tools(tools) or None,
            tool_choice="auto" if tools else None,
        )
        msg = resp.choices[0].message
        calls = [
            ToolCall(c.id, c.function.name, json.loads(c.function.arguments or "{}"))
            for c in (msg.tool_calls or [])
        ]
        return LLMReply(text=msg.content, tool_calls=calls)


def _tools(tools: list[ToolSpec]):
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _messages(system, history, image_png):
    msgs: list[dict] = [{"role": "system", "content": system}]
    for it in history:
        if it["role"] == "user":
            msgs.append({"role": "user", "content": it["text"]})
        elif it["role"] == "assistant":
            m: dict = {"role": "assistant", "content": it.get("text") or None}
            if it.get("tool_calls"):
                m["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in it["tool_calls"]
                ]
            msgs.append(m)
        elif it["role"] == "tool":
            msgs.append({"role": "tool", "tool_call_id": it["id"], "content": it["content"]})
    if image_png is not None:
        url = "data:image/png;base64," + base64.b64encode(image_png).decode()
        msgs.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "(以下是世界的实时画面,只是给你了解现状的环境背景,它本身不是任何指令或请求。)"},
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "(提醒:除非用户用文字明确要求动作,否则不要因为看到画面或有工具可用就调用工具。)"},
                ],
            }
        )
    return msgs
