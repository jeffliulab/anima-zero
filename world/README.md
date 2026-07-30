# Connecting a new world to ANIMA

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

A **world** is a separate process serving its own HTTP endpoints. Between it and ANIMA run
**two completely different lines**, and the most common mistake when writing one is
**putting something on the wrong line**.

```
                     ┌────────────────────────────────────────────┐
   ANIMA brain ──①──▶│  /mcp     AWI: brain ↔ world, over MCP     │
                     │           everything the brain can see     │
   ANIMA web  ──②──▶ │  /stream  out-of-band: world ↔ human       │
   (a person          │  /status  the brain sees NONE of this      │
    watching)        └────────────────────────────────────────────┘
```

**One question decides it**: is this for the **brain**, or for a **person**?
For the brain → line ①. For a person → line ②. Getting it wrong raises no error and
crashes nothing. It just inflates your results, or has the brain reach for something that
does not exist — **the hardest kind of broken to notice.**

---

## ① AWI (`/mcp`) — the brain's line

Wrap your world object into a standard MCP server with `build_awi_mcp()` from `awi_mcp.py`.

⚠️ That file exists as a **byte-identical copy in every world directory** — worlds are
separate processes with their own virtualenvs and share no imports. Changing the protocol
means changing every copy; `tests/test_awi_mcp_copies.py` holds them to the byte. **When you
add a world, add it to that test's list** — this was missed when sim-house-nav arrived in
v0.9. The five copies had not in fact drifted, but that is exactly how the guard would have
stopped guarding.

| Channel | What you implement | What the brain gets | Required |
|---|---|---|---|
| **tools** | `capabilities() -> {"tools":[…]}` | Callable atomic actions, with JSON Schema | May be empty (an observe-only world) |
| **observation** | `observe() -> (state, image)` | The image and structured state, each turn | ✅ yes |
| **guidance** | A block of prose | Joined into the system prompt so the model can make sense of an unfamiliar world | Strongly recommended |
| **config** | `config() -> {"options":[…]}` | The world's current setup, read-only | Optional |

**Long actions.** A single primitive may take tens of seconds. Declare a keyword-only
`_progress` in your `invoke` signature and call `_progress(0.5, "grasped, moving to e4")`
while you work — the brain forwards it to the web page live, so nobody waits at a blank
screen. Worlds that do not declare it are unaffected.

### ⛔ What must never appear on AWI

**The world's god's-eye ground truth**: coordinates, room names, the map, a chess FEN,
"where you actually are". That goes out of band, on `/status`. Handing the brain a
god's-eye view gives away the very ability the world exists to test.

The test: **would a real robot carry this sensor?** A camera, IMU orientation, a laser
range, "have I fallen" — yes, those are fair. "I am in the living room" — no. That is what
*you* can see from outside.

---

## ② Out-of-band HTTP — the human's line

The brain sees **none** of this. Here go the live view for people to watch, the ground truth
for people to check against, the controls for people to operate.

| Endpoint | Purpose | Required |
|---|---|---|
| `GET /health` | Liveness. Drives the "online" dot; not counted as traffic | ✅ yes |
| `GET /` | A human page — open it and watch the world | Recommended |
| `GET /stream` | MJPEG live view (the default address when there is one) | If there is an image |
| `GET /streams` | **Which live views exist, and which of them the brain can see** (below — the easiest thing to get wrong) | Required beyond one |
| `GET /status` | ⚠️ God's-eye ground truth, **for humans only** | If you have ground truth |
| `GET /config` `POST /config` | Read/change the world's setup (the same content the AWI `config` channel declares) | If you declare `config` |
| `POST /reset` | Reset | Recommended |

### ⭐ The `awi` field on `/streams` (added in v1.0, and easy to miss)

```jsonc
[
  {"name": "head_front",   "label": "Head-front camera", "url": "/stream",       "awi": true},
  {"name": "third_person", "label": "Third-person chase", "url": "/stream/third", "awi": false}
]
```

- `awi: true` — **or omitted** — means this is the view the brain gets through `observe()`.
  Omitted counts as true, so **existing worlds need no change**.
- `awi: false` means a **spectator view for people only**; the brain cannot see it.

**Why it must be marked.** The web page splits the sensor area in two: "👁 What ANIMA sees"
above, "🎥 Only you can see this; ANIMA cannot" below. Leave it unmarked and a spectator view
gets filed under the first heading — **which is a lie**. Anyone watching will believe the
brain had that god's-eye view, and the demo is worth nothing.

**A spectator view is a feature of the world**, not of the web page. The world decides
whether to offer one, from what angle, mounted on which part of the robot. The page just
renders whatever `/streams` says; it has no concept of "third person". So adding one means
a `/stream/xxx` endpoint on the world plus `awi: false` in `/streams` — and not one line of
the frontend.

**⛔ Three places must agree** (`tests/test_third_person.py` pins each one against
sim-house-nav):

1. the spectator view **does not appear at all** in `observe()` — not even as a variable name;
2. `/streams` marks it `awi: false`;
3. it leaves only by its own stream endpoint, and the AWI layer (the world object) never
   touches it.

---

## Checklist for a new world

1. Write the world object: `capabilities()` / `observe()` / `invoke()`, optionally `config()`.
2. Copy `awi_mcp.py` from any existing world (**byte-identical — do not edit it**) and mount
   it at `/mcp` with `build_awi_mcp()`.
3. Add the out-of-band endpoints: `/health` at minimum, `/stream` if there is an image,
   `/streams` with `awi` marked if there is more than one.
4. Keep tunables in the world's own `config.py` under an env prefix nobody else uses
   (`SIMCHESS_`, `HOUSENAV_`, …). ⛔ A world **never imports the brain's config** — brain and
   body not importing each other is a rule of this project.
5. **Register it.** ⛔ Each of these is a *whole set*, so **append, never replace** (a T0 rule,
   learned on 2026-06-28: adding sim-chess dropped the world that was there out of the menu
   entirely — that world, sim-desk, was itself removed in v1.1.1, but the lesson is why this
   rule exists):
   - the default list in `worlds()` in `src/config.py`
   - `ANIMA_WORLDS` in `.env.example`
   - `COPIES` in `tests/test_awi_mcp_copies.py`
   - the start-up commands in the maintainer's run-commands notes
6. **Make the brain shake hands again after starting your world.** The capability list is
   cached at the first handshake, so if you change your tools without restarting the backend
   your new tool will **never** reach the model's tool sheet. Each world card on the web AWI
   page has a "re-handshake" button. To diagnose: `curl -s localhost:8000/api/awi` and look
   at the tool names the brain **actually** holds. (This cost seven experiments in v0.9 — a
   newly added look-around tool was invisible the whole time, and was briefly written off as
   "the model doesn't want to use it".)

## Existing worlds

| World | Port | What it is |
|---|---|---|
| `sim-chess` | 8102 | A simulated board (chess / gomoku / go) with a built-in computer opponent |
| `camera` | 8104 | One real camera (zero tools — it can only be looked through) |
| `sim-house-nav` | 8112 | House navigation: a robot finds rooms by sight; two switchable bodies |
| `computer` | — | A placeholder, not implemented |

> `gazebo-chess` (8106) moved to `soma-zero/sim/` on 2026-07-08 and is not in this directory.
> **Its copy of `awi_mcp.py` has no automated guard** — when you change the AWI protocol,
> remember to sync it by hand.
