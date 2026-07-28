<div align="center">

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# ANIMA Zero

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP-6f42c1.svg)](https://modelcontextprotocol.io)
[![MuJoCo](https://img.shields.io/badge/sim-MuJoCo-orange.svg)](https://mujoco.org)
[![Version](https://img.shields.io/github/v/tag/jeffliulab/anima-zero?label=version&color=lightgrey)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Overview

ANIMA Zero is the brain of an embodied robot. It thinks but never moves: it decides *what to do*,
and the body decides *how to move*.

Tell it "go to the living room". It has no map, no coordinates and no list of rooms — only the
camera on the robot's head. From that it works out where it is, picks a direction, and keeps
walking until it sees the room you asked for. The robot walks with a learned gait, so the legs
really step; nothing teleports.

<div align="center">
<img src="docs/images/nav-go2.gif" alt="ANIMA driving a quadruped through a house" width="820">
<br>
<sub>Left: the only input ANIMA gets. Right: what actually happens, which ANIMA never sees.</sub>
</div>

### Why "Zero"?

It is a series name, not a version number. **Zero means this line stays open source** —
the brain is ANIMA Zero, the body is SOMA Zero, and any future commercial edition will
carry a different name rather than closing this one. The whole project is MIT.

On PyPI it is `pip install anima-zero` and the import is `import anima` — `anima` alone was already registered by someone else.

## Key features

- **One brain, different bodies**: the same brain code drives a Unitree Go2 quadruped and a
  Unitree G1 humanoid without a line changing — only the eye height differs, 0.38 m against 1.25 m.
- **One interface for any world**: a world is a separate process speaking AWI over MCP. Swapping
  worlds means swapping a URL — and a world is untrusted until you have reviewed and approved it.
- **From a sentence to joint torques**: an instruction crosses five layers before it becomes leg
  motion, and those layers run three and a half orders of magnitude apart in frequency.
- **It remembers what it is doing**: two state registers ride along in the system prompt, so a
  sixty-step turn does not forget the goal or what it has already ruled out.
- **Auditable and interruptible**: every frame, thought and tool call is recorded, and a running
  turn can be stopped mid-flight.

<div align="center">
<img src="docs/images/eye-go2.png" alt="Quadruped view" width="400">
<img src="docs/images/eye-g1.png" alt="Humanoid view" width="400">
<br>
<sub>The same living room through the quadruped's eyes (left) and the humanoid's (right).
What a robot can see decides what it can conclude, which is why the scene is built realistically
rather than tailored to one machine.</sub>
</div>

## Architecture

A world is a program of its own — a simulator today, real hardware later. ANIMA never reaches
inside it. Everything the brain knows arrives through four channels, and everything it does leaves
through the same four. A human can also bypass the brain entirely and poke the world in its own UI,
which is the clearest proof that the two are genuinely separate.

<div align="center">
<img src="docs/images/arch-overview.svg" alt="Human, ANIMA and the world, with AWI in between" width="860">
</div>

The three endpoints along the bottom — ground truth, video and liveness — never travel over MCP and
never reach the brain. That separation is deliberate: the moment ground truth enters perception,
the ability this world is meant to test is given away for free.

Inside a single instruction the layering becomes concrete. The brain reasons once per step; the
gait policy runs at 50 Hz; physics at 500 Hz. That gap is what System 2 and System 1 actually mean
here, and it is why the brain can only ever issue intent, never joint angles.

<div align="center">
<img src="docs/images/command-journey.svg" alt="From one sentence to joint torques" width="860">
</div>

The world reports back truthfully rather than conveniently. A learned gait does not track a velocity
command exactly — a turn drifts, a walk falls short — so the world measures what actually happened and
says so, and the brain corrects its own sense of position from that rather than from what it asked for.

```text
src/core/      orchestrator, AWI contract, trust store, safety gate
src/clients/   MCP client layer and the world registry
src/session/   sessions, context window, unified log
src/llm/       model adapters      src/presentation/  HTTP backend
world/         the worlds, each its own process
services/      board-game engine   frontend/  web app   eval/  scoring
```

## Installation

```bash
uv tool install anima-zero     # or: pipx install anima-zero, or plain pip
anima demo
```

That starts a world, connects a brain, and drops you into a conversation. No API key, no
node, nothing else to install. The brain it uses does not think — it calls one tool and
reports back — because the point of the demo is to show you the loop, not to impress you.
Add a key and `anima demo --brain gpt-5.4` to see the same loop with a brain that does.

```text
anima demo                    one command, something happens
anima chat --world W          a conversation in the terminal
anima run --say "..."         one turn, scripted
anima serve                   the backend API, for the web app
anima world add NAME URL      register a world — and review it before approving
anima doctor                  what is configured and what is reachable
```

### The full setup

Three processes: a world, the backend, and the web app. Scenes and robots come from
alice-house, looked up next to this repository; set `HOUSENAV_ASSETS_ROOT` if it is elsewhere.

```bash
cd world/sim-house-nav && pip install -e . && uvicorn server:app --port 8112
pip install -e . && cp .env.example .env      # add an API key, or point at a local Ollama
anima serve
cd frontend && npm install && npm run dev
```

### Connecting a world is a trust decision

A world is a remote process, and its own description of itself lands in the brain's system
prompt — so its tools and guidance do not reach the brain until you have looked and said
yes. `anima world add NAME URL` prints what it declares, then asks. Approval binds to the
content, not the name: if the world comes back different you are asked again, with a note
on what changed. While developing your own world, set `ANIMA_TRUST_ALL=1`.
[SECURITY.md](SECURITY.md) says what this does and does not protect against.

## Running the demo

Open the web app, create a session against `sim-house-nav`, and type "go to the living room".
The middle column shows what the robot sees and, separately, a chase camera that only you can
see. The right column shows every step: frame, reasoning, tool call, and the world's answer.

<div align="center">
<img src="docs/images/ui-chat-en.png" alt="The ANIMA web app" width="880">
</div>

To check whether a claim is true rather than plausible, ask the world directly —
`curl -s localhost:8112/status`, an endpoint for human verification that never enters perception.
Swapping things costs one line each: the body has a dropdown on the AWI dashboard (or set
`HOUSENAV_ROBOT=g1` before starting the world), the brain has one in the web app, and the world is
chosen when you create a session.

These worlds ship with the repository:

| World | Port | What it is |
|---|---|---|
| [sim-house-nav](world/sim-house-nav) | 8112 | An apartment and a walking robot, quadruped or humanoid |
| [sim-chess](world/sim-chess) | 8102 | A chess set that holds the only ground truth and plays back |
| [sim-desk](world/sim-desk) | 8100 | A desk, a pen and a canvas |
| [camera](world/camera) | 8104 | A real webcam, with no tools at all — look but never touch |

### How well it actually works

Five target rooms, one run each, every final frame checked by hand against what the model claimed:

| Target | Steps | Result |
|---|---|---|
| Kitchen | 9 | Correct — fridge, counter and wall cabinets all in frame |
| Living room | 5 | Correct — TV, sofa and floor lamp, not arguable |
| Master bedroom | 34 | Wrong — a marble floor was read as a "white mattress" |
| Bathroom | 40 | Wrong — that was the kitchen |
| Laundry | 60 | Unfinished — hit the per-turn step ceiling |

The interesting result is the negative one. The suspected cause used to be that a kitchen and a
bathroom look alike from 0.38 m, which is part of why the humanoid was added. But the humanoid, at
1.25 m, sees the hob and the range hood clearly and still calls it a bathroom. So this is not a
perception problem: facing the same doorway, the model composes whatever story matches the room it
is hunting for. The next release aims at the acceptance criterion instead.

Runs that did work, with per-frame verification, are written up in
[world/sim-house-nav/实测记录.md](world/sim-house-nav/实测记录.md).

## Add your own world

Implement a standard MCP server with the four channels above, add its address to `ANIMA_WORLDS`, and the
brain will drive it unchanged. The smallest version is three methods — `capabilities()`, `observe()` and
`invoke()` — wrapped in the `awi_mcp.py` adapter that ships with every world. Copy from
[sim-desk](world/sim-desk) for the simplest case or [sim-house-nav](world/sim-house-nav) for the complete
one, and read [world/README.md](world/README.md) first. The contract is written down in
[docs/awi-spec-v1.md](docs/awi-spec-v1.md), and `anima conformance <url>` checks a world against it.

## Acknowledgements

Scenes, robot models and locomotion policies come from [alice-house](https://github.com/jeffliulab/alice-house).
The humanoid's turning policy was trained in [unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion).
Physics is [MuJoCo](https://mujoco.org); the robot models originate from
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie).
