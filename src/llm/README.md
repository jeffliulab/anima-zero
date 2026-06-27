# 如何给 ANIMA 增加一个语言大脑

这个目录(`src/llm/`)是 ANIMA 的**大脑层**:把"具体哪家 LLM"和编排器解耦。编排器只认一个统一接口
(`LLM` 协议),不关心背后是 Claude、OpenAI 还是本地 Ollama。所以**加一个新大脑,编排器、object、前端都不用动**。

本目录现有文件:

| 文件 | 作用 |
|---|---|
| `base.py` | 统一接口 `LLM` 协议 + 中立类型(`ToolCall` / `LLMReply`) |
| `openai_compat.py` | `OpenAICompatLLM` —— 一切走 **OpenAI 兼容口**的(OpenAI 云端 + 本地 Ollama) |
| `claude.py` | `ClaudeLLM` —— Anthropic 自家 SDK |
| `factory.py` | `make_llm()` 选脑 + `list_brains()` 报告每个脑是否配置好 |

---

## 一、大脑要满足的契约(`LLM` 协议)

任何大脑类都要有这三样(见 `base.py`):

```python
class LLM(Protocol):
    vision: bool   # 能不能看图。ANIMA 是具身大脑,必须 True(见末尾红线)
    model: str     # 模型名/tag,给日志和前端显示用
    def chat(self, system: str, history: list[dict],
             tools: list[ToolSpec], image_png: bytes | None) -> LLMReply: ...
```

`chat()` 的输入:
- `system` —— 系统提示(编排器拼好的)。
- `history` —— **中立格式**的对话历史(每家自己翻译成自家格式),item 形如:
  - `{"role": "user", "text": ...}`
  - `{"role": "assistant", "text": ..., "tool_calls": [ToolCall, ...]}`
  - `{"role": "tool", "id": ..., "name": ..., "content": ...}`
- `tools` —— 当前可调的能力清单(`ToolSpec`,带 JSON Schema)。
- `image_png` —— 当前画面(可能是 `None`,表示没连 object、纯聊天)。

`chat()` 的输出:一个 `LLMReply`
```python
LLMReply(text="给人看的话(可空)", tool_calls=[ToolCall(id, name, arguments_dict), ...])
```
有 `tool_calls` → 编排器执行后再循环;没有 → 当作最终回复返回给用户。

> 你要做的,就是在 `chat()` 里把中立的 `system/history/tools/image_png` **翻译成目标家的请求**,
> 调它的 API,再把它的回复**翻译回** `LLMReply`。`openai_compat.py` 和 `claude.py` 就是两个现成范例。

---

## 二、情况 A:新大脑走 OpenAI 兼容口 → 不写新类,只在 factory 加一行

绝大多数服务(OpenAI、本地 Ollama、各种「OpenAI 兼容」的云/自托管网关)都能直接复用 `OpenAICompatLLM`,
它的构造是 `OpenAICompatLLM(model, base_url, api_key)`。只需在 `factory.py` 的 `_registry()` 登记表里加一项:

```python
# 例:接一个 OpenAI 兼容的云服务
"my-vlm": {"label": "My VLM", "model": "some-vision-model", "kind": "api",
           "build": lambda: OpenAICompatLLM(
               os.getenv("MY_VLM_MODEL", "some-vision-model"),
               os.getenv("MY_VLM_BASE_URL", "https://api.example.com/v1"),
               os.getenv("MY_VLM_API_KEY", "")),
           "ready": lambda: bool(os.getenv("MY_VLM_API_KEY"))},

# 例:再加一个本地 Ollama 视觉模型(复用现成的 ollama 地址 + 查模型是否已 pull)
"llava": {"label": "LLaVA 13B", "model": os.getenv("ANIMA_LLAVA_MODEL", "llava:13b"), "kind": "local",
          "build": lambda: OpenAICompatLLM(os.getenv("ANIMA_LLAVA_MODEL", "llava:13b"), ollama, "ollama"),
          "ready": lambda: ollama_ready(os.getenv("ANIMA_LLAVA_MODEL", "llava:13b"))},
```

然后做第四节的两步登记即可。

---

## 三、情况 B:新大脑是另一套 SDK / 协议 → 新建一个文件

如果目标家不是 OpenAI 兼容(自有 SDK、自有请求格式),就照着 `claude.py` 在本目录新建一个文件,
写个类实现 `LLM` 协议。骨架:

```python
# src/llm/my_provider.py
from __future__ import annotations

import base64

from ..object import ToolSpec
from .base import LLMReply, ToolCall


class MyProviderLLM:
    vision = True

    def __init__(self, model: str):
        import my_sdk  # 该家的 SDK
        self.model = model
        self.client = my_sdk.Client()  # 一般在这里读自家的 API key 环境变量

    def chat(self, system, history, tools, image_png) -> LLMReply:
        # 1) 把 history 翻译成该家的 messages 格式
        # 2) 把 tools(ToolSpec)翻译成该家的工具/函数声明
        # 3) image_png 有的话,按该家的多模态格式塞进去(base64 / data-uri / 文件…)
        resp = self.client.create(model=self.model, system=system, messages=..., tools=...)
        # 4) 把该家的回复翻译回 LLMReply
        text = ...
        calls = [ToolCall(id=..., name=..., arguments=...) for c in ...]
        return LLMReply(text=text, tool_calls=calls)
```

> 工具调用如果该家支持不好,可改用「受约束 JSON 输出」:不发 tools,改成在 prompt 里要求按某个 schema
> 吐一个动作 JSON,并用该家的 `response_format` / grammar 锁死格式,自己 parse 后构造 `ToolCall`。

---

## 四、登记两步(两种情况都要做)

### 1. 在 `factory.py` 的 `_registry()` 表里加一项
就是上面那种 `{label, model, kind, build, ready}` 的字典,key 是大脑名字(前端下拉 / API 传的 `brain`
用它)。`make_llm()`(创建大脑)和 `list_brains()`(报告版本号 + 配没配好)都从这张表派生——
**只此一处,版本号不重复**。
- `model`:版本号,会显示在前端下拉里。
- `ready`:是否配置好。在线脑看 key 在不在(`bool(os.getenv("XX_API_KEY"))`);本地 Ollama 脑用现成的
  `ollama_ready(模型名)`(查模型是否已 pull)。

### 2. 在 `../.env.example` 里加配置说明
把新大脑要的环境变量(key / base_url / model 版本号)按现有风格写清楚,方便别人 clone 下来照填。

---

## 五、一条红线:必须能看图

ANIMA 是**具身机器人的大脑**,连上 object 后每一轮都会拿到画面(`image_png`)。所以新大脑**必须是视觉模型**
(`vision = True`,并真的把 `image_png` 喂进去)。纯文本模型(只会读字、看不了图)**不要接**——
它在"连了 object、要看着画面操作"的场景里没法用。

---

## 六、加完自检清单

- [ ] 起后端不报错;`GET /api/brains` 里能看到它、带版本号,配置好后 `available` 变 `true`。
- [ ] `GET /api/check?brain=<新名字>` 配置好后返回 `ok:true`。
- [ ] 前端下拉能选到它、标着版本号;没配置时标「(未配置)」但仍可选,选中会提示未配置。
- [ ] 连上桌面说一句"把笔移到右上角",它能看着画面调 `move_pen`,左边画面更新。
