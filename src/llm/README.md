# Adding a language brain to ANIMA

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

This directory (`src/llm/`) is ANIMA's **brain layer**: it keeps *which LLM* away from the
orchestrator. The orchestrator knows one interface — the `LLM` protocol — and not whether
Claude, OpenAI or a local Ollama sits behind it. So **adding a brain changes nothing in the
orchestrator, the worlds or the frontend**.

What is here:

| File | Role |
|---|---|
| `base.py` | The `LLM` protocol and its neutral types (`ToolCall` / `LLMReply`) |
| `openai_compat.py` | `OpenAICompatLLM` — anything speaking the **OpenAI-compatible API** (OpenAI itself, local Ollama, most gateways) |
| `claude.py` | `ClaudeLLM` — Anthropic's own SDK |
| `mock.py` | `MockLLM` — a scripted brain, so the whole chain runs with no key and no network |
| `factory.py` | `make_llm()` builds a brain; `list_brains()` reports which ones are configured |

---

## 1. The contract (`LLM` protocol)

Any brain provides these three things (see `base.py`):

```python
class LLM(Protocol):
    vision: bool   # can it see images? ANIMA is an embodied brain, so this must be True
    model: str     # model name/tag, shown in logs and in the UI
    def chat(self, system: str, history: list[dict],
             tools: list[ToolSpec], image_png: bytes | None) -> LLMReply: ...
```

Into `chat()`:

- `system` — the system prompt, already assembled by the orchestrator.
- `history` — the conversation in a **neutral format**, which each brain translates into its
  own. Items look like:
  - `{"role": "user", "text": ...}`
  - `{"role": "assistant", "text": ..., "tool_calls": [ToolCall, ...]}`
  - `{"role": "tool", "id": ..., "name": ..., "content": ...}`
- `tools` — the callable capabilities right now (`ToolSpec`, carrying a JSON Schema).
- `image_png` — the current frame, or `None` when no world is connected and it is just chat.

Out of `chat()`: an `LLMReply`.

```python
LLMReply(text="prose for the human (may be empty)", tool_calls=[ToolCall(id, name, arguments_dict), ...])
```

With `tool_calls`, the orchestrator executes them and loops. Without, the text is the final
reply to the user.

> Your job in `chat()` is to translate neutral `system` / `history` / `tools` / `image_png`
> **into** that provider's request, call it, and translate its answer **back** into an
> `LLMReply`. `openai_compat.py` and `claude.py` are two worked examples.

---

## 2. Case A: the provider is OpenAI-compatible → one line in the factory

Most services — OpenAI, local Ollama, the many "OpenAI-compatible" cloud and self-hosted
gateways — reuse `OpenAICompatLLM` directly. It is constructed as
`OpenAICompatLLM(model, base_url, api_key)`. Add an entry to the `_registry()` table in
`factory.py`:

```python
# an OpenAI-compatible cloud service
"my-vlm": {"label": "My VLM", "model": "some-vision-model", "kind": "api",
           "build": lambda: OpenAICompatLLM(
               os.getenv("MY_VLM_MODEL", "some-vision-model"),
               os.getenv("MY_VLM_BASE_URL", "https://api.example.com/v1"),
               os.getenv("MY_VLM_API_KEY", "")),
           "ready": lambda: bool(os.getenv("MY_VLM_API_KEY"))},

# another local Ollama vision model — reuse the existing address, check the model is pulled
"llava": {"label": "LLaVA 13B", "model": os.getenv("ANIMA_LLAVA_MODEL", "llava:13b"), "kind": "local",
          "build": lambda: OpenAICompatLLM(os.getenv("ANIMA_LLAVA_MODEL", "llava:13b"), ollama, "ollama"),
          "ready": lambda: ollama_ready(os.getenv("ANIMA_LLAVA_MODEL", "llava:13b"))},
```

Then do the two registration steps in §4.

---

## 3. Case B: the provider has its own SDK → a new file

If it is not OpenAI-compatible, add a file here modelled on `claude.py` with a class
implementing the `LLM` protocol. The skeleton:

```python
# src/llm/my_provider.py
from __future__ import annotations

import base64

from ..core.awi import ToolSpec
from .base import LLMReply, ToolCall


class MyProviderLLM:
    vision = True

    def __init__(self, model: str):
        import my_sdk  # the provider's SDK
        self.model = model
        self.client = my_sdk.Client()  # usually reads its own API-key env var here

    def chat(self, system, history, tools, image_png) -> LLMReply:
        # 1) translate history into the provider's message format
        # 2) translate tools (ToolSpec) into its tool/function declarations
        # 3) if image_png is present, attach it the way this provider wants it
        #    (base64 / data URI / file upload …)
        resp = self.client.create(model=self.model, system=system, messages=..., tools=...)
        # 4) translate the reply back into LLMReply
        text = ...
        calls = [ToolCall(id=..., name=..., arguments=...) for c in ...]
        return LLMReply(text=text, tool_calls=calls)
```

> If the provider's tool calling is weak, use **constrained JSON output** instead: send no
> tools, ask in the prompt for one action object matching a schema, lock the shape with the
> provider's `response_format` or grammar support, and build the `ToolCall` yourself after
> parsing.

---

## 4. Registration, two steps (both cases)

### 4.1 Add an entry to `_registry()` in `factory.py`

The `{label, model, kind, build, ready}` dictionary above, keyed by the brain's name — that
key is what the UI dropdown shows and what the API's `brain` field carries. Both
`make_llm()` (build a brain) and `list_brains()` (report version and readiness) derive from
this one table, so **the version string is written once**.

- `model` — the version string, shown in the dropdown.
- `ready` — is it configured? For hosted brains, whether the key exists
  (`bool(os.getenv("XX_API_KEY"))`). For local Ollama brains, `ollama_ready(model)`, which
  checks the model has been pulled.

### 4.2 Document its settings in `../../.env.example`

Write the new brain's environment variables — key, base URL, model version — in the style of
the existing entries, so somebody cloning the repo can fill them in.

---

## 5. One hard rule: it must be able to see

ANIMA is the brain of an **embodied robot**. With a world connected it receives a frame every
turn (`image_png`). So a new brain **must be a vision model** — `vision = True`, and it must
genuinely pass `image_png` through. **Do not add a text-only model.** It cannot do the one
thing this system is for: looking at what is in front of it and acting on that.

---

## 6. Checklist

- [ ] The backend starts. `GET /api/brains` lists it with its version, and `available` turns
      `true` once configured.
- [ ] `GET /api/check?brain=<name>` returns `ok: true` once configured.
- [ ] The dropdown offers it with its version. Unconfigured, it is marked as such but still
      selectable, and selecting it says so.
- [ ] Connected to the sim-chess world, "play a move" makes it look at the image, call `move`,
      and the picture on the left changes.
