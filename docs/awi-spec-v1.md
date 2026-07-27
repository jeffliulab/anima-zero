<div align="center">

<a href="awi-spec-v1.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="awi-spec-v1_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# AWI v1 — the Anima World Interface

**Status**: stable. **Version**: 1. **Checker**: `anima conformance <url>`.

AWI is the contract between a **brain** and a **world**. A brain thinks and never moves; a
world holds the physics and is the only thing that is true. They run as separate processes
and share no code — only this contract.

This document says what a world must do to be driven by ANIMA without ANIMA changing. It is
written against the implementation, and the implementation is the arbiter: `src/core/awi.py`
holds the types, `awi_mcp.py` (a byte-identical copy in each world) maps them onto MCP, and
`src/clients/world_client.py` is the client. Where prose and code disagree, the code is
right and this document is a bug.

The words **must**, **should** and **may** are used in the ordinary IETF sense. `anima
conformance` reports a **must** as a failure and a **should** as a recommendation, and
recommendations do not fail a run.

---

## 1. Scope, and what is deliberately not here

AWI covers **everything the brain can perceive or do**. That is a small surface on purpose:

| In AWI | Not in AWI |
|---|---|
| What actions exist, and their arguments | How the world is built, deployed or reset |
| What the robot can sense right now | Where the robot actually is |
| The world's own description of itself | Anything a person watches, clicks or checks |

The second column is real and necessary — it just travels on ordinary HTTP beside AWI, never
through it. §4 covers it.

⛔ **The load-bearing line in this whole specification**: a world must not put its
**god's-eye ground truth** on AWI. Coordinates, room names, the map, the chess position,
"where you actually are". The test is not what is convenient — it is **would a real robot
carry this sensor?** A camera, IMU heading, a laser range, "have I fallen over" — yes. "I am
in the living room" — no; that is what *you* see from outside.

Nothing enforces this. Break it and nothing errors, nothing crashes, and your results get
better. That is exactly why it is stated first.

## 2. Transport and handshake

A world is a standard **MCP server** speaking **Streamable HTTP**, mounted at **`/mcp`** on
its base URL. The brain connects with the official MCP SDK, calls `initialize`, and uses
`tools/*`, `resources/*` and `prompts/*` from there.

Worlds **must** accept the MCP `initialize` handshake at `/mcp`. Everything else in this
document is unreachable until that works, and `anima conformance` stops there if it fails.

> ⚠️ **Implementation note that has bitten this project**: run the session manager with
> `json_response=False` (SSE response mode). In JSON mode the SDK waits for the response and
> discards `notifications/progress` outright, which silently breaks progress reporting for
> long actions (§5.3). Do not "simplify" it back.

## 3. The four channels

### 3.1 Tools — what the world can do

Declared through MCP `tools/list`, invoked through `tools/call`.

Each tool **must** carry:

| Field | Requirement |
|---|---|
| `name` | Non-empty. This is how the brain calls it. |
| `inputSchema` | A JSON Schema with `"type": "object"` — **even with no parameters** (`{"type": "object", "properties": {}}`). Arguments are named. |

Each tool **should** carry:

- a `description` of three or four sentences saying **when to call it and when not to**. This
  is not documentation; it is the entire basis on which a model decides. A tool with no
  description gets called at the wrong moments.
- a `readOnlyHint` annotation (see §6 for what that does and does not mean).

The world **may** declare zero tools. An observe-only world is valid and useful — the
`camera` world has none, and "it can look and cannot act" is thereby structural rather than
something a prompt was asked to enforce.

`tools/call` returns `isError` to express failure: a refused move is `ok: false`, which
arrives as `isError: true` with a human-readable message. Structured data goes in
`structuredContent`.

⛔ **Report failure honestly.** The brain's entire recovery strategy — look again, try
something else, ask a person — is built on being told the truth about what happened. A world
that reports a failed grasp as a success has removed the brain's ability to recover, and it
will keep acting on a picture of the world that is wrong.

### 3.2 Observation — what the robot senses

Read through MCP `resources/read` on **`anima://observation`**. This is the **one required
channel**: a world the brain cannot look at is not a world it can be embodied in.

The response **must** be:

1. **First**, a text content whose body is a **JSON object** — the state. A mapping of named
   readings. An empty `{}` is valid and sometimes the point: `sim-chess` gives exactly that,
   because it intends the brain to read the board with its eyes and nothing else.
2. **Then**, zero or more image blobs, each with mime type **`image/png`**.

A world with nothing to show **must** send no blob. ⛔ **Never fabricate a frame.** The brain
is told "no picture at the moment", which is a state it can act on; a made-up image is a
state it cannot detect.

**Multiple cameras.** Blobs carry no names, so **their order is the only thing tying a
picture to a camera**. A world with more than one **must** list the names in
`state["cameras"]` in **exactly** the order the blobs are sent, and **must** generate both
from the same list. Get this wrong and the brain silently attributes each picture to the
wrong camera — nothing errors anywhere in the system, which is why `anima conformance`
checks the counts.

### 3.3 Guidance — the world describing itself

Read through MCP `prompts/get` on the prompt named **`guidance`**. Prose written by the
world's author: what this world is, how its tools are meant to be used, what its state means,
how to go about doing something useful here.

The brain joins this into its **system prompt**. That is what keeps ANIMA generic — a world
explains itself, rather than the brain carrying special cases for it — and it is also why
connecting a world is a trust decision (§6).

Guidance **should** exist. Without it the model meets your world with no idea what it is.

⛔ **Do not put the answers in it.** For sim-house-nav the guidance says there are rooms to
find; it does not say which rooms exist or what is in them. Writing that would hand over the
very thing the world was built to test. This is a rule about *your experiment*, not about the
protocol — no checker can catch it.

### 3.4 Config — the world's setup (optional)

Read through MCP `resources/read` on **`anima://config`**. Shape:

```jsonc
{"options": [
  {"key": "robot", "label": "Body", "description": "which robot stands in the house",
   "value": "go2", "choices": [{"value": "go2", "label": "Go2 quadruped"},
                               {"value": "g1",  "label": "G1 humanoid"}]}
]}
```

Each option **must** have a `key`, and **should** have a current `value`.

This channel exists because some setups are neither an action nor a perception. Which robot
stands in the house is not something the brain should call a tool to change, and it is not
something that varies frame to frame — the two existing channels had nowhere to put it.

⛔ **It is read-only over AWI.** *Changing* configuration goes over the world's own
out-of-band HTTP (`POST /config`, in the same category as `/reset`), because changing it is a
**person's** action. The brain is simply told what body it now has, the way a real robot knows
what body it is.

## 4. Out of band — everything the brain cannot see

Ordinary HTTP on the world's base URL, never through MCP. The brain sees none of it.

### 4.1 `/health` (required)

`GET /health` **must** answer 200. The online indicator polls it. Without it a world reads as
permanently offline no matter what else works. It is deliberately not counted as AWI traffic,
or the traffic view would be nothing else.

### 4.2 `/streams` and the `awi` field

`GET /stream` is the MJPEG live view. A world with more than one **must** serve `/streams`:

```jsonc
[
  {"name": "head_front",   "label": "Head-front camera",  "url": "/stream",       "awi": true},
  {"name": "third_person", "label": "Third-person chase", "url": "/stream/third", "awi": false}
]
```

`awi: true` — **or omitted**, so existing single-view worlds need no change — means this is
what the brain actually receives through `observe()`. `awi: false` means a spectator view for
people only.

With more than one view, every entry **must** declare `awi`. The web page splits the sensor
panel into "what ANIMA sees" and "only you can see this". An unmarked spectator view is filed
under the first heading, which tells everyone watching that the brain had a god's-eye view it
never had. That is not a display bug; it is a false claim about the experiment.

### 4.3 Others (recommended)

`GET /` a human page · `GET /status` ⚠️ god's-eye ground truth, **for people checking results
only** · `GET /config` `POST /config` read and change setup · `POST /reset`.

## 5. What the host does with what you send

Worth knowing, because it changes how you should write a world.

### 5.1 The handshake is cached

The brain reads a world's capabilities **once**, at the first handshake, and reuses them.

⛔ **Change your tools and you must restart the brain backend**, or nothing has changed. The
world will have the new tool and the brain will still be holding the old list, so it never
reaches the model's tool sheet. To check what the brain **actually** has:
`curl -s localhost:8000/api/awi`. This cost seven experiments once — a new tool went unused
and it looked like the model was declining to use it, when it had never been offered.

### 5.2 Text from a world is capped, and guidance is fenced

Guidance is capped (`ANIMA_WORLD_GUIDANCE_MAX_CHARS`, 4000) and tool descriptions are capped
(`ANIMA_WORLD_TOOL_DESC_MAX_CHARS`, 1000). Over the cap, ANIMA truncates and tells the model
it truncated. A well-behaved world is nowhere near these; they exist for hostile or runaway
text.

Guidance is also wrapped in fence markers and labelled to the model as **material, not
instruction**, which cannot override the rules above it. Fence markers are stripped from the
world's own text so it cannot close the fence early and have the rest read as ANIMA's own
words.

### 5.3 Long actions report progress

A physical primitive can take tens of seconds. Declare a keyword-only `_progress` in your
`invoke` signature and call it while you work:

```python
def invoke(self, name, *, _progress=None, **args):
    ...
    _progress(0.5, "grasped, moving to e4")
```

It is detected by signature inspection at build time, so worlds that do not declare it are
unaffected. Progress travels as MCP `notifications/progress`, reaches the user's screen live,
and — importantly — **counts as a sign of life**: the brain does not time an action out on a
fixed deadline but on silence. Reported progress extends the deadline; going quiet for
`ANIMA_WORLD_LIVENESS_TIMEOUT` seconds ends it; and `ANIMA_WORLD_INVOKE_HARD_CAP` caps it
regardless.

## 6. ⭐ Trust — `kind` is a declaration, not a guarantee

Anyone writing a world needs to know how the host treats what they send.

**Your text goes to the model's highest-authority channels.** Guidance is joined into the
system prompt; tool descriptions become the function-calling tool sheet. Connecting a world
means allowing it to write into the brain's system prompt — which is why ANIMA requires an
explicit human approval before any of it reaches the model.

**Approval binds to content, not to a name.** The first time a world is connected, everything
it declares — every tool's name, kind, description and schema, plus the guidance **in full** —
is put in front of the operator, who decides. What is recorded is the SHA-256 of that
manifest. Unchanged, and nobody is asked again; **changed, and they are asked again and shown
what changed**. Same idea as SSH pinning a host key or Docker pinning an image digest.

**What this means for you as a world author**: your manifest hash changes whenever you edit a
tool description or your guidance, and reconnecting will ask for approval again. During
development set `ANIMA_TRUST_ALL=1`, which skips approval entirely. Local development only —
never in anything shared or published.

**Until approved, a world contributes nothing.** It still lists and still reports whether it
is online, so the operator can go and approve it. But its guidance never enters the system
prompt and its tools never enter the tool sheet.

### `kind` and `readOnlyHint`

A tool declares `kind`: `"tool"` (atomic action), `"read"` (read-only perception) or
`"judge"` (deterministic adjudication). `read` and `judge` map to MCP `readOnlyHint: true`.

⛔ **This is what you say about your tool, not a fact the host has verified.** It was, once,
treated as fact — the orchestrator consulted the safety gate only for tools the world had not
marked read-only, which meant a world could skip the gate entirely by annotating a
destructive tool as read-only. That was reclaimed in v1.1: **every world action now goes to
the gate**, with `kind` as one input to the decision and never a bypass. It was harmless while
the gate was open in simulation, and a hole the day it is switched on for real hardware.

Declare `kind` honestly anyway. Not because the framework depends on it, but because it is
what the operator reads when deciding whether to approve you.

## 7. Compatibility

**Within v1, this contract only grows.** New optional channels, new optional fields, new
annotations — anything already working keeps working. A change that breaks an existing world
gets a new major version, not a v1 revision.

Both new channels so far arrived this way: `anima://config` in v1.0 and the `awi` field on
`/streams` in v1.0, both optional, both defaulting to the old behaviour when absent.

## 8. Checking your world

```bash
anima conformance http://localhost:8100
```

It connects, exercises every channel, and reports each check against the section of this
document it comes from. Exit code 0 when conformant; recommendations do not fail it.

⛔ **What it cannot tell you.** It checks the *shape* of the contract. It cannot check
**truthfulness** and does not pretend to: whether your state leaks a god's-eye view, whether
`kind` matches what a tool really does, whether your guidance is honest. No automated check
decides those. A person does, at approval time — which is the whole reason approval exists.

A green report means your world speaks the protocol. It does not mean your world is safe to
connect, and it is not evidence for anyone else that it is.

---

**See also**: [`world/README.md`](../world/README.md) for building one step by step ·
[`SECURITY.md`](../SECURITY.md) §2 for the trust model from the operator's side ·
[`ROADMAP.md`](../ROADMAP.md) for what is known not to work.
