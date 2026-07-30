# Anima Zero Changelog

<a href="CHANGELOG.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="docs/i18n/zh/CHANGELOG.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>
<a href="docs/i18n/ja/CHANGELOG.md"><img src="https://img.shields.io/badge/%E8%A8%80%E8%AA%9E-%E6%97%A5%E6%9C%AC%E8%AA%9E-bf3989?style=flat-square" alt="日本語"></a>

Release notes for ANIMA Zero. **Keep them short: per version, only what actually changed.**
(Format after [Keep a Changelog](https://keepachangelog.com).)

## [1.1.0] — 2026-07-27

Main: from a portfolio repository into a project other people can install, connect to and
write worlds against — the whole repository relicensed to **MIT** (by writing our own way out
of the last non-permissive dependency), `pip install anima-zero` followed by a real `anima`
command and a web app, **a world treated as an untrusted remote party**, and AWI turned into a
written specification with a checker.

Features:

1. **Relicensed to MIT; the commercial dual-licensing offer is retired.** What stood in the
   way was GPL-licensed python-chess, so we **wrote our own rules library**
   (`packages/anima-chess` — bitboards and Zobrist hashing, MIT): perft matches the published
   values on all six standard positions, and a midgame depth-3 search takes 1.27 s against the
   advisory's 1.5 s cap. ⚠️ It is **two to four times slower** than python-chess — enough for
   that one purpose and not for anything deeper; the cause and the fix are logged as ROADMAP
   R5. The test suite passes with python-chess uninstalled. All 69 dependencies audited: none
   non-permissive.
2. **It installs and it runs**: `pip install anima-zero` gives you the `anima` command
   (`demo` / `chat` / `run` / `serve` / `doctor` / `world` / `conformance`). The web app is
   statically exported and **travels inside the wheel**, so `anima serve` hands you an
   interface on a machine with no node. A **built-in desk world** and a **mock brain needing no
   key** ship with it, so `anima demo` shows the whole loop in one command: frame, decision,
   tool call, result. ⚠️ Releasing is now coupled to building the UI (`build_ui.py` before
   `python -m build`), and `anima serve` prints the web app's build timestamp — because
   **shipping a package with a stale interface is something nobody would ever notice.**
3. **⭐ A world is treated as an untrusted remote party.** A world's guidance is joined into
   the brain's **system prompt** and its tool descriptions become the **tool sheet** — all of it
   text somebody else wrote. So: a world's content **does not reach the brain until you have
   read it and approved it** (it still lists, and still shows whether it is online); approval
   **binds to a manifest hash** (SHA-256 over the URL, every tool's name, kind, description and
   schema, and the guidance in full), and **a changed manifest asks you again and tells you what
   changed** — which is what defeats a rug pull; guidance is **fenced** before entering the
   system prompt and labelled as material rather than instruction, with the fence markers
   stripped from the world's own text, and length caps applied. ⛔ The **safety gate was also
   taken back from the world**: the orchestrator used to consult it only for tools the world
   had not marked read-only, so a world could **skip the gate entirely** by annotating a
   destructive tool as `readOnlyHint: true`. Every action now goes to the gate, with `kind` as
   one input to the decision. Harmless while the gate stood open in simulation, and a hole the
   day it is closed for real hardware. `ANIMA_TRUST_ALL=1` is a development escape hatch. The
   whole threat model is pinned by a malicious-world fixture (`tests/test_world_trust.py`).
   ⚠️ **Prompt injection is mitigated, not solved** — see ROADMAP R3.
4. **AWI became a specification**: `docs/awi-spec-v1.md` (English and Chinese) states every
   channel, what is required against what is recommended, and what the host does with what a
   world sends — including a section on **`kind` being a declaration rather than a guarantee**.
   With it comes `anima conformance <url>`, which connects to a world, exercises every channel
   and reports each check against the section it comes from — including the **multi-camera
   ordering** check, which earns its place because image blobs carry no names, their order is
   the only thing tying a picture to a camera, and a mismatch is silent everywhere else.
   ⛔ It **states its own limits every time**: whether the state leaks a god's-eye view, whether
   `kind` matches behaviour, whether guidance is honest — no automated check settles those. A
   person does, at approval time.
5. **Language, split by audience**: everything a model reads — system prompt, tool
   descriptions, state blocks, every world's guidance — is now **English in a single version**,
   collected in `src/prompts.py`, ending with one line asking it to reply in the user's
   language. Documents people read come in both. The CLI and the web app default to English.
   ⚠️ **That is a behaviour change and the benchmark that would settle it has not been re-run** —
   the five-room navigation comparison, before and after, is an acknowledged debt recorded as
   ROADMAP R2. Until it exists, "English is better here" is a hypothesis. If it turns out
   worse, the rollback point is one file. ⚠️ The first pass missed a great deal — the
   orchestrator's world blocks, the image framing sent with every frame, the safety gate's
   reasons, the truncation notices, every backend error the web app displays, and the mock
   brain's own replies were all still Chinese while this claim was already written down.
   They were found by installing the wheel and running it, not by reading the source. What
   is left, and why, is ROADMAP R6.
6. **Machine guards, and debts on the record**: `scripts/selfcheck.py` turns four house rules
   that lived only in a local notebook into CI guards (the orchestrator stays free of
   task-specific logic / no dead config / no unregistered placeholders / the version agrees in
   three places), and **every one was negative-tested** — the dead-config guard was broken in
   its first version and would have stayed green forever untested. New `ROADMAP.md` (both
   languages): **not a wish list, but the mirror of measured failures and deliberate debts**,
   each numbered — R1 confirmation bias, R2 the unmeasured prompt language switch, R3 injection
   not solved, R4 four high-severity CVEs in the frontend's npm tree, R5 the chess library's
   speed.

**Measured limits, recorded honestly**: cross-room navigation is **unchanged** from v1.0 — five
targets, two right, two wrong, one unfinished. Nothing in this release aimed at it. This
version was about whether anyone else can use the project, not about how clever it is.
ROADMAP R1 is what aims at the rest.

## [1.0.1] — 2026-07-26

Main: fixes two faults in the v1.0 panel — it had no height limit and squeezed the session
list out of the sidebar entirely, and it was in the wrong place.

1. **Height-capped and collapsible**: the number of notes is unbounded (default capacity 20),
   and without a cap twelve notes measurably crushed the session list to a sliver.
2. **Moved above the conversation**: it is the state of the **current session**, but it sat at
   the bottom of the sidebar among the **global** items (runtime parameters, AWI dashboard,
   appearance) — looking global, and half a screen away from the session it belonged to.
   Pinning it above the conversation also means **it does not scroll away**, so through a long
   turn you can always see what it is doing; collapsed it takes one line and doubles as a
   status bar (with a core task it simply shows "working on ⋯").
3. **Dropped "working memory" as an umbrella term**: the phrase appears nowhere in the code and
   made people think the core task and the notebook were one thing. They are now shown as what
   they are — the **core task** (what I am doing, one sentence, updated by rewriting) and the
   **notebook** (what I have found, entry by entry, updated by adding and removing).

## [1.0.0] — 2026-07-26

Main: the robot can **change bodies, remember its way, and not walk into furniture** — the
world went from "a dog" to "a body you can swap" (a Unitree G1 humanoid was added, with a
turning policy trained specifically for it), the brain gained a general working memory, and AWI
gained a formal channel. At the same time **the list of answers fed to the brain was deleted
outright**: what this world tests is working out which room you are in by looking, and a score
obtained by handing over the answers means nothing.

Features:

1. **One world, two bodies**: `sim-house-nav` hard-codes nothing for the quadruped any more —
   model, policy, camera, spawn height and how torque is sent all come from the asset library's
   robot manifest (⛔ the two are **opposite**: explicit PD for the quadruped, implicit PD for
   the humanoid; get it backwards and it falls immediately). The humanoid has 29 degrees of
   freedom and an eye height of 1.25 m, and sees a completely different room from the same
   place. A **turning policy was trained specifically for it** (yaw command range widened from
   ±0.2 to ±0.8, 10,000 iterations) — ⚠️ it still **cannot pivot on the spot** (standing still,
   the policy takes the cheaper option), so turning carries 0.3 m/s of forward speed and a 90°
   turn moves it 0.6–0.8 m along. The world **reports that displacement honestly**.
2. **A new AWI channel for world configuration**: a world **declares** what it can be configured
   with (the new MCP resource `anima://config`), and a person changes it over **out-of-band
   HTTP** — changing configuration is a human action, and the brain is only told what body it
   now has, the way a real robot knows what body it is. ⛔ The prompt says plainly that it
   cannot change this: the brain has no tool for it, and implying otherwise only makes it reach
   for something that does not exist. This also fixed the v0.9 trap where capabilities are
   cached at the first handshake, so a world that gained a tool without a backend restart never
   got it onto the tool sheet — the web app now has a re-handshake button.
3. **A notebook register, and the answer key removed**: the core task holds "what I am doing"
   (one sentence) and the new notebook holds "what I have found" (entries added and removed).
   Both are injected permanently and do not slide out as the conversation grows. All three
   refusals — empty, too long, full — say why, and **never truncate or discard silently**. At
   the same time the world's guidance lost its furniture inventory and landmark table for
   twelve rooms (1180 → 844 characters). ⚠️ **Measured: removing the answers changed nothing**
   (two of five targets, as before) — so that list had never been doing any work. And the
   notebook made the actual cause visible for the first time: it describes whatever is behind a
   door as the room it is currently looking for. Confirmation bias.
4. **Laser ranging, braking, and a chase camera**: eight-way ranging enters perception (a real
   Go2 carries an L1 lidar on its head), and walking forward it brakes and stands when it gets
   too close, reporting honestly how much room is left — ⛔ it stops, it does not steer; where to
   go next is always the brain's decision. The third-person chase view is **for humans only**:
   `/streams` marks each view with `awi`, the web page splits the sensor panel accordingly, and
   filing the chase view under "what ANIMA sees" would be a lie. Tests pin the line.
5. **The world contract became a template** (`world/README.md`): the two lines, AWI and
   out-of-band, and one question to tell them apart — is this for the brain or for a person?
   Plus six machine guards checking registration completeness (is the world in `.env.example`,
   is it in the drift-guard list, do multi-view worlds mark `awi`, …).

**Measured limits, recorded honestly**: short-range navigation is solid (quadruped "go to the
kitchen" in 10 steps / 41 s, "go to the living room" in 9 steps / 32 s; the humanoid got both
too). But **cross-room navigation is still unreliable**: of five targets, two right, two wrong,
one unfinished — the same for both bodies. ⭐ This release **disproved v0.9's hypothesis about
the cause**: the suspicion was that a kitchen and a bathroom look alike from a low viewpoint,
but the humanoid at 1.25 m sees the hob and the range hood clearly and **still calls it a
bathroom**. So it is not that it cannot see. It is confirmation bias: facing the same doorway,
it composes whatever story fits the room it is hunting for. The next release aims at the
acceptance criterion (describe first and classify second; tighten what "I can see it, so I have
arrived" may mean), not at perception. Runs that did work are in
`world/sim-house-nav/实测记录.md`.

## [0.9.0] — 2026-07-25

Main: a new world, **sim-house-nav** — a Unitree Go2 quadruped in a house, where ANIMA sees only
the forward camera on its head and must judge where it is from the furniture and direct it
there. Along with it, "a turn" was widened from **one move and stop** to **one thing, finished**,
and long turns got a brake.

Features:

1. **The new sim-house-nav world (:8112)**: a real quadruped gait in MuJoCo — three navigation
   primitives (forward, left, right) are translated into velocity commands `(vx, vy, wz)` fed to
   a trained policy, so the dog genuinely steps rather than teleporting. The primitives execute
   **closed loop** (a learned gait tracks a velocity command at only about 83% and 62%, so it
   measures as it goes and stops when it has arrived) and report honestly when a wall blocks it.
   The observation carries **the picture, IMU heading and whether it has fallen** — ⛔ no
   coordinates and no room names; rooms have to be recognised by looking. Scenes and robot
   models moved out into a separate asset library, mounted by configuration.
2. **A turn is one thing** (a revision of 0.8's item 1, not a repeal of the discipline): when a
   turn ends is **decided by ANIMA producing prose**. The step limit went from 8 to 60 and a
   900-second wall-clock limit was added, both demoted to **seatbelts rather than metronomes**.
   In chess, "one thing" is still one move (2–6 steps, ending naturally, behaviour unchanged);
   in navigation it is finding the target room (tens of steps, run to convergence). ⛔ v0.7's
   rejected "play a whole game from one sentence" is still rejected — that was **several things**
   crammed into one turn, which has nothing to do with the step limit.
3. **A brake and a window for long turns**: session-level interruption
   (`POST /api/sessions/{sid}/interrupt`), with the web app's Send turning into Stop while
   generating. Interruption reaches into the wait for an action, so pressing it does not mean
   waiting for the dog to finish the step. Hitting a limit is a polite pause (the core task
   stays on the register and "continue" resumes), and each of the three reasons says its own
   piece. The thinking panel got a scrolling height cap, step numbers and expand/collapse, and
   the core runtime parameters sit permanently at the bottom left, read from the backend rather
   than written into the frontend.
4. **Making it remember what it is doing**: the system prompt and the world guidance gained
   "finish one thing in one go", "for a multi-step task, register the core task first" and
   "write progress back to the register as you go" — in a long turn, frames seen earlier slide
   out of context, and this register is the only thing that does not.

**Measured limits, recorded honestly**: short-range navigation works — "go to the kitchen",
found and identified in 7 steps / 45 s. But **cross-room navigation is not yet reliable**: four
target rooms, one run each, one right and three wrong (two misidentified rooms, one stopped
halfway), and it goes in circles over longer distances. From a low viewpoint the kitchen and
the bathroom are hard to tell apart (both are "worktop, cupboard doors, white panel"). The
fourth primitive `look_around` was implemented but has **never been measured** — the brain
caches capabilities at the first handshake, and it never reached the tool sheet during the
experiments.

## [0.8.0] — 2026-07-25

1. The maximum steps per turn is stated as 8 by default. For now the system is strictly
   turn-based; long loops are out of scope.
2. Central configuration moved to pydantic-settings: type validation that fails fast, every
   parameter with a description and a lower bound. Environment variable names and the
   `config.*` consumer interface are unchanged, and `.env` now affects **every** parameter (it
   previously reached only the world and service lists).

## [0.7.0] — 2026-07-06

Main: the gazebo-chess world grew the ability to **play a whole game** — from one sentence
ANIMA plays a complete game on its own (tens of moves of physical pick-and-place, with
captures, castling and promotion all going through real primitives), while the world holds a
referee and a teleporting computer opponent, and the final game record is filed for scoring.
**Not a line of the brain changed** — only `ANIMA_MAX_STEPS` went up — which is itself the field
test of the claim that swapping worlds costs a URL.

Features:

1. **A whole game**: the gazebo-chess world holds a **referee** (a legality gate before the arm
   moves, ground truth advanced only after each primitive is physically verified, game-over
   detection and a filed game record) and a **teleporting computer opponent** (it answers the
   moment the brain completes a move, without announcing what it played, so the brain has to see
   it — a third independent engine copy, which must not be merged with the other two), plus
   captured pieces going into a bin and **recovery from a spare** (when a piece leaves the board
   permanently, placing an identical piece back on its square realigns the position with the
   record) and a "new game" button. Zero changes on the brain side; two complete games measured
   (38 and 44 moves). Final records feed the scorer, which reports primitive success rate and
   latency per world — physical failures and illegal moves are never merged. The old
   single-demo-piece mode without a FEN behaves exactly as before.
2. **Every square reachable, and real pieces**: grasping moved to **radial tilt** plus geometry
   measured directly (10 cm from the axis, 4.5 cm squares — both measured defaults, both
   env-overridable) → **all 64 squares reachable**, fixing v0.5's "the whole h-file is
   unreachable" (`scripts/reach_map.py` reproduces it in one command). **Retry diversity** turns
   a deterministically cursed square into one that succeeds on the first change of posture.
   Pieces became **real Staunton meshes** (CC-BY 4.0, source and licence in the repository;
   collision bodies unchanged).
3. **A session core-task register** (the only brain-side change, and a general mechanism): an
   endurance run measured the failure — the task slides out of the context window and the brain
   stops halfway. "What task am I on" is **state**, not chat history. The LLM registers,
   rewrites and clears it **itself** through the built-in meta-tools `set_core_task` and
   `clear_core_task` (no keywords, no pinning, no heuristics), and it is injected permanently
   into the system prompt as a state channel rather than occupying the history window.
   Turn-based behaviour is unchanged: it stops after each move and waits.
4. **Licence change**: the whole repository went from Apache-2.0 to **AGPL-3.0 plus commercial
   dual licensing.** What matters about AGPL-3.0 is that **providing a service over a network**
   also requires opening the corresponding source. Closed-source commercial integrations
   unwilling to take that on could contact the maintainer for a commercial licence. Compatible
   with GPL-3 python-chess; releases up to v0.6.0 remain available under the original
   Apache-2.0.
   > ⚠️ **Superseded by v1.1**: the whole repository is **MIT** from v1.1, and the commercial
   > dual licensing is retired with it (MIT already permits closed-source commercial use).
   > What made that possible was replacing python-chess with our own MIT rules library.
   > Releases v0.7.0–v1.0.1 remain under the AGPL-3.0 terms they shipped with. The full licence
   > history is in [NOTICE](NOTICE).

## [0.6.0] — 2026-07-03

Main: the engines were brought in-tree and world and service fully decoupled, with service
mounting returning to standard MCP "host assembly" — cleaning the boundaries before aiming at
real hardware. In short: host and services are now independent of one another. The engine
server talks to the ANIMA host, the world server talks to the ANIMA host, and the world server
and the engine server no longer talk at all.

Features:

1. The three board-game engine cores (chess, gomoku, go) moved into
   `services/boardgame_engine/` — they previously read files in another repository through
   importlib, so a fresh clone could not start. The service was renamed boardgame-engine, the
   three chess tools are live, and go and gomoku are in place awaiting a consumer. The external
   `3-anima-chess-engine` folder was deleted; the repository stands on its own.
2. The brain's engine adviser and the sim-chess world's built-in computer opponent were split
   into two deliberately independent copies (`chess_engine.py` and `chess_bot.py`, sharing no
   code, and not to be merged): with the engine service switched off the world's computer plays
   on, and the adviser travels with the brain across bodies.
3. v0.5's "a world declares its services" (`anima://services`) was abolished in favour of the
   brain mounting them itself through `config.services()`, symmetrically with `worlds()` — in
   line with the MCP principle that which servers to connect is the host's business and servers
   do not know one another. Pairing is done by the model looking at the picture and choosing a
   tool, not by structural binding.
4. Unified naming for the three MCP layers and the "dedicated line" model: there are exactly two
   kinds of server — the **World Server** (reality, all three primitives) and the **Engine
   Server** (an adviser, tools only). The host (the ANIMA brain) opens one dedicated line to
   each, which is the client layer (`RemoteWorld` / `RemoteService` in the code, one line to one
   server). A line remembers the address, caches capabilities at the handshake, translates the
   protocol, manages timeouts by role (liveness supervision for a world, a short question timeout
   for an engine) and keeps the books. Lines do not talk to each other, which is how server
   isolation is realised. README §4 and the `/awi` page were updated to match.

## [0.5.0] — 2026-07-03

Main: a large refactor — human-designed orchestration such as game mode was deleted, minimising
the framework in order to examine the intelligence: the LLM looks at the picture itself, decides
each step itself, and calls the tools itself.

Features:

1. **Liveness semantics for long actions** (a framework correction): a physical action takes tens
   of seconds, v0.4's fixed timeout killed it, and worlds ran the work on the event loop so a
   single move froze the entire world server. Adopted **MCP progress notifications** instead:
   the world runs tool execution on a worker thread and reports human-readable progress in
   stages, and the brain **extends the deadline on progress, declares death only on silence, and
   caps the total**. This generalises to any world with slow atomic actions.
2. LangGraph became the substrate for the ReAct orchestration, replacing the naive in-house
   version.
3. The chess engine became a service. A service differs from a world in that a service answers
   questions for ANIMA (an adviser) while a world receives ANIMA's commands (reality). Services
   were declared by the world itself (`anima://services`) and mounted automatically at the
   handshake.
4. Game mode, behaviour trees and the whole skill layer were deleted: chess is ordinary
   conversation again (say "your move"), and reading the board, calculating and decomposing are
   all decided by the LLM on the spot. Observe–think–act became the only main loop.
5. Unified session logs: LLM calls, world traffic and service calls are merged per session into
   one stream, viewable and copyable by session in the frontend.
6. Multiple cameras became first class: one perception may carry several named pictures, and the
   frontend shows the live views side by side. gazebo-chess gained two cameras and a legible
   board (squares and edge coordinates), and "take that off / put this on / put it there" was
   measured end to end from language to action.

## [0.4.0] — 2026-07-02

Main: a Gazebo chess interface, teleoperation, and Cartesian motion of the gripper.

Features:

1. The in-house HTTP AWI was dropped in favour of the standard MCP server. The old perceive,
   invoke and guidance scheme became Tools, Resources and Prompts.
2. The chess engine stopped being part of a chess skill and became an MCP server of its own.
3. A new world, gazebo-chess: a Gazebo simulation built on the Episode1 model — the stand-in for
   SOMA Zero — with a simulated gripper and pieces.
4. Cartesian motion implemented, and teleoperated grasping of a piece succeeded.

## [0.3.0] — 2026-06-30

Main: a real camera world, letting ANIMA see the real physical world for the first time. A light
release, mostly testing the stream from a real camera.

Features:

1. A new world, camera, with settable resolution.
2. Details of the chess skill adjusted.
3. Debugging and interface: the anima-logs page had a session-attribution bug that made
   "view by session" permanently empty; fixed, and gained one-click copying of a whole session
   with all fields shown. The frontend gained a light theme and a switch, and AWI and anima-logs
   became panels embedded in the home page.

## [0.2.0] — 2026-06-30

Main: a new simulated board program, sim-chess, and a chess skill. The agent orchestration
framework was worked out.

Features:

1. A new world, sim-chess, able to simulate gomoku, chess, go and other boards. ANIMA sees only
   sim-chess's picture, never its internal state.
2. A chess mode in ANIMA's interface: entering it starts a looping behaviour-tree mode in which
   ANIMA plays on continuously without the user having to speak each time.
3. Human-in-the-loop and evaluation designed, with a simple proof of concept.
4. The top-down abstraction "Orchestrator → Skill → (Skill) Adapter → Behaviour Tree → Tools"
   settled.
5. AWI's three core requests settled: perceive, invoke and capabilities.

## [0.1.0] — 2026-06-27

Main: the first release of ANIMA Zero. The framework was rewritten completely, replacing the
earlier ANIMA O1 prototype and reusing none of its code.

Features:

1. The core architecture of separating cognition from world: ANIMA as a cognitive system does
   the thinking and deciding, a world as an independent entity does the sensing and executing,
   and the two meet across the standard AWI protocol.
2. The concept of a "world" defined: a world can be any independent entity — a program, a robot,
   an environment — and ANIMA communicates with it and operates it over AWI.
3. A first chat interface for ANIMA, with sessions, memory kept locally, and the ability to
   switch brains mid-conversation.
4. The first example world, sim-desk: a virtual desk, a pen and a canvas, offering three
   capabilities — move the pen, draw, erase — to validate the whole protocol, with the picture
   streamed to ANIMA.

## [Anima O1] — Before 2026-06-27

ANIMA O1 was an early design. It was torn down entirely during ANIMA Zero's development and
rebuilt from nothing, so its details are not recorded here. ANIMA O1 and the early SOMA work
settled the System 1 / System 2 direction, and laid the conceptual groundwork for ANIMA Zero and
SOMA Zero.
