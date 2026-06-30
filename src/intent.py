"""意图分类（脑内、通用）—— 用 LLM 做**结构化枚举**判断，绝不扫关键词、绝不用 yes/no 词表。

为什么不扫词：把"用户想干嘛"这种语义决策交给 LLM（项目硬规则）；但**解析 LLM 的回答也不能写死词表**
（"yes/是/对"→True 这类一旦换说法就失效、还脆）。正解：让 LLM 直接吐一个 `{"intent": "<枚举之一>"}`，
代码只读这个字段、并校验它确实是给定枚举之一。换技能/换语言都不用改解析。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .llm import LLM


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text or "", re.S)
    return m.group(0) if m else "{}"


def classify(llm: LLM, situation: str, message: str,
             choices: dict[str, str]) -> Optional[str]:
    """从 `choices`（枚举值 -> 一句话释义）里选最贴切的一个意图。

    返回选中的枚举键；LLM 出错/没选中合法值 → None（调用方据 None 走兜底，不静默猜）。
    """
    if not choices:
        return None
    opts = "；".join(f'"{k}"={v}' for k, v in choices.items())
    prompt = (f"{situation}\n用户说：「{message}」\n"
              f"从这些意图里选**最贴切的一个**：{opts}。\n"
              '只输出一行 JSON：{"intent":"<上面枚举值之一>"}')
    try:
        r = llm.chat("你是意图分类器，只输出一行 JSON，intent 必须是给定枚举值之一，别的不说。",
                     [{"role": "user", "text": prompt}], [], None)
        data = json.loads(_extract_json(r.text or ""))
        choice = data.get("intent")
        return choice if choice in choices else None
    except Exception:
        return None
