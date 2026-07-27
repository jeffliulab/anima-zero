<div align="center">

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# ANIMA Zero

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP-6f42c1.svg)](https://modelcontextprotocol.io)
[![MuJoCo](https://img.shields.io/badge/sim-MuJoCo-orange.svg)](https://mujoco.org)
[![Version](https://img.shields.io/badge/version-v1.0-lightgrey.svg)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-AGPL--3.0-yellow.svg)](LICENSE)

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

## Key features

- **One brain, different bodies**: the same brain code drives a Unitree Go2 quadruped and a Unitree
  G1 humanoid without a single line changing. Only the eye height differs, 0.38 m against 1.25 m.
- **One interface for any world**: a world is a separate process that speaks AWI over MCP. Swapping
  worlds means swapping a URL.
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

The world reports back truthfully rather than conveniently. A humanoid cannot pivot on the spot, so
its turn carries a little forward speed and ends up 0.64 m further along; the world says so, and the
brain corrects its own sense of position from that.

```
src/core/         orchestrator, AWI contract, safety gate, interrupt
src/clients/      MCP client layer and the world registry
src/session/      sessions, context window, unified log
src/llm/          model adapters
src/presentation/ HTTP backend
world/            the worlds, each its own process
services/         the board-game engine advisor
frontend/         web app, bilingual
eval/             reproducible scoring from game logs
```

## Installation

Three processes run together: a world, the backend, and the web app.

```bash
# 1. a world — house navigation, pure MuJoCo, no ROS and no conda needed.
#    Scenes and robots come from alice-house, looked up next to this repository;
#    set HOUSENAV_ASSETS_ROOT if it lives elsewhere.
cd world/sim-house-nav && pip install -e . && uvicorn server:app --port 8112

# 2. the backend
pip install -e .
cp .env.example .env          # add an API key, or point it at a local Ollama
uvicorn anima.presentation.server:app --port 8000

# 3. the web app
cd frontend && npm install && npm run dev
```

## Running the demo

Open `localhost:3000`, create a session against `sim-house-nav`, and type "go to the living room".
The middle column shows what the robot sees and, separately, a chase camera that only you can see.
The right column shows every step: the frame, the reasoning, the tool call, and what the world
answered.

<div align="center">
<img src="docs/images/ui-chat-en.png" alt="The ANIMA web app" width="880">
</div>

To check whether a claim is true rather than plausible, ask the world directly. This endpoint is for
human verification only and never enters perception:

```bash
curl -s localhost:8112/status
```

Swapping things around costs one line each. The body has a dropdown on the AWI dashboard, or set
`HOUSENAV_ROBOT=g1` before starting the world. The brain has a dropdown in the web app. The world is
chosen when you create a session, and the list lives in `ANIMA_WORLDS`.

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
perception problem; facing the same doorway the model composes whatever story matches the room it is
currently hunting for. The next release aims at the acceptance criterion instead.

Runs that did work, with per-frame verification, are written up in
[world/sim-house-nav/实测记录.md](world/sim-house-nav/实测记录.md).

## Add your own world

Implement a standard MCP server with the four channels above, add its address to `ANIMA_WORLDS`, and
the brain will drive it unchanged. The smallest version is three methods — `capabilities()`,
`observe()` and `invoke()` — wrapped in the `awi_mcp.py` adapter that ships with every world. Copy
from [sim-desk](world/sim-desk) for the simplest case or [sim-house-nav](world/sim-house-nav) for the
complete one, and read [world/README.md](world/README.md) first.

## Acknowledgements

Scenes, robot models and locomotion policies come from [alice-house](https://github.com/jeffliulab/alice-house).
The humanoid's turning policy was trained in
[unitree-g1-locomotion](https://github.com/jeffliulab/unitree-g1-locomotion).
Physics is [MuJoCo](https://mujoco.org); the robot models originate from
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie).
