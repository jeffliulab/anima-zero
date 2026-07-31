"""OpenAI 云端 + 本地 Ollama —— 都走 OpenAI 兼容接口,改 base_url 即可切换。"""
from __future__ import annotations

import base64
import json

from ..core.awi import ToolSpec
from .. import prompts
from .base import LLMReply, ToolCall, norm_images


class OpenAICompatLLM:
    def __init__(self, model: str, base_url: str | None, api_key: str,
                 vision: bool = True):
        from openai import OpenAI

        self.model = model
        # vision=False 告诉主循环「这个脑看不见」：画面照常进会话留痕给人看，
        # 但不喂给它（纯文本模型收到 image_url 轻则浪费 token、重则直接报错）。
        self.vision = vision
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
        return LLMReply(text=msg.content, tool_calls=calls, usage=_usage(getattr(resp, "usage", None)))


def _usage(u) -> dict | None:
    """OpenAI 用量 → 归一 {input, output, total}。拿不到则 None。"""
    if u is None:
        return None
    inp = getattr(u, "prompt_tokens", 0) or 0
    out = getattr(u, "completion_tokens", 0) or 0
    return {"input": inp, "output": out, "total": getattr(u, "total_tokens", inp + out) or (inp + out)}


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
            # content 必须是字符串：哪怕这一回合只调了工具、没有文字，也给空串而非 None。
            # OpenAI 协议不接受 content=null（即便带 tool_calls），qwen3-vl / gpt-5.5 都会 400。
            m: dict = {"role": "assistant", "content": it.get("text") or ""}
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
    imgs = norm_images(image_png)
    if imgs:
        content: list = [{"type": "text",
                          "text": prompts.IMAGE_FRAMING}]
        for name, png in imgs:   # 多相机：每张图前标注它来自哪路相机（名字来自世界的 state.cameras）
            if name:
                content.append({"type": "text", "text": prompts.IMAGE_CAMERA_LABEL.format(name=name)})
            content.append({"type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}})
        content.append({"type": "text",
                        "text": prompts.IMAGE_NO_ACTION_REMINDER})
        msgs.append({"role": "user", "content": content})
    return msgs
