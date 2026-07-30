# AGENTS.md — agent entry point for this repository

Read this file first, then jump to the section your task needs. It is an index, not a manual: the
prose documents it points at are the authority, and they are all in the repository.

## What this is (and is not)

**ANIMA Zero is the brain of an embodied robot — System 2.** It thinks and never moves: it decides
*what to do*, while a separately running **world** (System 1) decides *how to move*. The two never
share code; they talk over **AWI**, a contract carried on MCP. MIT licensed. On PyPI it is
`pip install anima-zero`, and the import is `import anima`.

It is **not**:

- a robot controller — nothing here runs a real-time control loop, and real-time control never goes
  over MCP;
- a chess program or a navigation stack — those live in worlds and in advisory engine services;
- domain-specific in any way: **the framework hard-codes nothing about any particular world.** If you
  are about to teach the brain something about chess or houses, you are in the wrong layer.

## Where a fact belongs (the layering rule)

Everything below the first row is where task-specific knowledge is *allowed* to live. Ask yourself:
**would this code still make sense against a different world?** If not, it belongs further down.

| Layer | Where | Task-specific knowledge? |
|---|---|---|
| Orchestrator — the generic ReAct / LangGraph loop | `src/core/orchestrator.py` | ⛔ **never.** Not one line about a game, a room or a move |
| Safety gate & world trust | `src/core/safety.py`, `src/core/trust.py` | ⛔ never — it reasons about action *kinds* and approvals, not about tasks |
| MCP client side — registry, world and service connections | `src/clients/` | ⛔ never |
| Session, prompts, messages, LLM adapters | `src/session/`, `src/prompts.py`, `src/messages.py`, `src/llm/` | ⛔ never (task wording comes from the world's own guidance) |
| **World** — a separate process; physics and the only ground truth | `world/<name>/` | ✅ yes — it *is* the domain |
| **Engine service** — a high-level advisor answering questions | `services/boardgame_engine/` | ✅ yes |

`python scripts/selfcheck.py` enforces the first row; CI runs it on every push.

## Task → where to look

| You want to… | Read |
|---|---|
| understand the architecture and see it running | [`README.md`](README.md) |
| know the house rules, the language split and the commit format | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| write a world, or check one you wrote | [`docs/awi-spec-v1.md`](docs/awi-spec-v1.md), [`world/README.md`](world/README.md), then `anima conformance` |
| connect a world safely | [`SECURITY.md`](SECURITY.md) §2 — connecting a world is a **trust decision**, not a config change |
| add or register an LLM | [`src/llm/README.md`](src/llm/README.md) and the table in `src/llm/factory.py` |
| change a tunable number | `src/config.py` — every knob lives there with a description, overridable by env |
| see what changed in a release | [`CHANGELOG.md`](CHANGELOG.md) · direction: [`ROADMAP.md`](ROADMAP.md) |

## Repo map

| Path | What |
|---|---|
| `src/core/` | the generic loop, the AWI contract types, the safety gate, world trust, interrupts |
| `src/clients/` | MCP client side: world client, service client, registry, bridge |
| `src/session/` | session state, context, and the session log every turn is recorded in |
| `src/llm/` | brain adapters (OpenAI-compatible, Claude, mock) behind one factory |
| `src/presentation/` | the backend API (`anima serve`) the web app talks to |
| `src/worlds/desk/` | the one world shipped *inside* the package, so `anima demo` leads somewhere |
| `world/` | the worlds that ship with the repo as separate processes — `sim-house-nav` (8112), `sim-chess` (8102), `sim-desk` (8100, submodule), `camera` (8104). `world/computer/` is a **reserved idea folder with no code**: not registered anywhere, nothing to start |
| `services/boardgame_engine/` | the advisory engine service (a "thinks about the game" server, never a controller) |
| `packages/anima-chess/` | a standalone chess rules library, published separately |
| `frontend/` | the web app |
| `eval/`, `tests/`, `docs/` | evaluation harness, test suite, the AWI spec + translated docs + doc checkers |

Two files that look like duplicates are **deliberately separate copies with different roles**:
the engine's `chess_engine.py` (the brain's advisor) and `world/sim-chess/chess_bot.py` (the world's
opponent). Do not merge them; the isolation is the point and it is verified by test.

## How to run it

```bash
uv tool install anima-zero && anima demo    # one command, no key, no node

anima chat --world W        # a conversation in the terminal
anima serve                # the backend API for the web app
anima world add NAME URL    # register a world — review it before approving
anima doctor               # what is configured, what is reachable
anima conformance URL      # check a world against the AWI v1 contract
```

Full three-process setup (a world, the backend, the web app) is in the README; configuration lives in
[`.env.example`](.env.example). `world/sim-desk` is a **git submodule** — clone `--recursive`. Scenes
and robots for `sim-house-nav` come from
[alice-house](https://github.com/jeffliulab/alice-house), looked up next to this repo or via
`HOUSENAV_ASSETS_ROOT`.

Before opening a pull request:

```bash
pytest -q
ruff check .
python scripts/selfcheck.py           # house rules, incl. orchestrator cleanliness
python docs/check_readme.py           # if you touched any README
cd frontend && npx tsc --noEmit       # if you touched the web app
```

## Red lines

The full set with the reasoning is in [`CONTRIBUTING.md`](CONTRIBUTING.md); these are the ones that
get broken most often:

- ⛔ **The orchestrator stays task-agnostic.** Task knowledge goes into the world.
- ⛔ **Whole sets are appended to, never replaced** — `ANIMA_WORLDS`, `.env.example`, default lists,
  README tables, the language list in the doc checkers. This is a hard rule because it has been
  broken: adding one world once removed another from the UI entirely.
- ⛔ **No hard-coding.** Paths are derived or come from the environment; tunable numbers go in
  `src/config.py`; anything the model should judge — intent, whether to stop, which move — is judged
  by the model, never by a keyword list.
- ⛔ **A placeholder is declared, never buried**, and **claimed tests or capabilities must exist**. A
  comment saying something is covered when it is not is the same lie as faking data.
- ⛔ **The brain never holds ground truth.** It does not compute the game, referee itself, or trust its
  own memory of the world over what the world reports.
- ⚠️ Commands that touch **real hardware** carry physical risk and are run by a person who is present
  at the machine — never by an agent on its own.

Commits here carry **no `Co-Authored-By`** trailer, and the message format (English first, then
Chinese) is in `.gitmessage`. Push and tag only when the maintainer asks.

---

If a `CLAUDE.md` sits next to this file in your local working copy, read it too — it holds the
maintainer's internal working notes and is deliberately not part of the repository.
