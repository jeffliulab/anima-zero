<div align="center">

<a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="CONTRIBUTING_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# Contributing

> ANIMA Zero is an **open research prototype** — a portfolio and teaching project, MIT
> licensed (see [LICENSE](LICENSE)). It is mostly moved forward by its maintainer, but
> issues, feedback, small fixes and documentation improvements are welcome. Please read
> [`README.md`](README.md) for the architecture and the
> [code of conduct](CODE_OF_CONDUCT.md) first.

## What this is

ANIMA is the **brain** of an embodied robot: System 2, it thinks and never moves. It
observes and operates a separately running **world** (System 1) across an interface called
**AWI**, carried over MCP. The framework is domain-agnostic — it hard-codes nothing about
any particular world.

## Running it locally

```bash
uv tool install anima-zero && anima demo     # nothing else needed, no key, no node
```

For development, three processes: a world, the backend, the web app — see the README.
Configuration (API keys, a local Ollama address, the world list) is in
[`.env.example`](.env.example). `world/sim-desk` is a **git submodule**, so clone with
`--recursive` or run `git submodule update --init` afterwards.

## Adding something

- **A new world.** A world is a standard **MCP server** (mounted at `/mcp`) speaking three
  primitives: **Tools** (what it can do), **Resources** (perception, `anima://observation`)
  and **Prompts** (its own guidance). Add its address with `anima world add NAME URL` and
  the brain drives it without a line changing. Start from
  [`world/sim-desk`](world/sim-desk) for the simplest case or
  [`world/sim-house-nav`](world/sim-house-nav) for the complete one, and read
  [`world/README.md`](world/README.md) first.
- **A new brain (LLM).** See [`src/llm/README.md`](src/llm/README.md). Most models speak
  the OpenAI-compatible protocol; register yours in the table in `src/llm/factory.py`.
- **A tool.** Tools are declared by the world in MCP's `tools/list`: a name, three or four
  sentences saying **when to call it and when not to**, a JSON Schema, and a `kind`. The
  framework passes them to the model as native function calls — never hand-write JSON into
  a prompt.

## House rules

Most of these exist because something went wrong once. They are enforced by
`python scripts/selfcheck.py`, which CI runs on every push.

- **The orchestrator stays task-agnostic.** `src/core/orchestrator.py` must not know what
  game or task it is driving. Task-specific knowledge belongs in the world. When unsure:
  *would this code still make sense against a different world?*
- **Whole sets are appended to, never replaced.** `ANIMA_WORLDS`, `.env.example`, default
  lists, README tables — adding an entry must not drop an existing one. This is a hard
  rule because it has been broken: adding one world once removed another from the UI
  entirely.
- **No hard-coding.** Paths are derived or come from the environment. Tunable numbers go in
  `src/config.py` with a description, not inline. Anything the model should judge —
  intent, whether to stop, which move — is judged by the model, never by a keyword list.
- **A placeholder is declared, never buried.** If you must leave one, say so in the pull
  request.
- **Claimed tests and capabilities must exist.** A comment saying something is covered,
  when it is not, is the same lie as faking data.

### Language

The split is by **audience**, and it is deliberate:

| What | Language |
|---|---|
| Text a **model** reads — system prompt, tool descriptions, a world's guidance | **English only.** See `src/prompts.py` for why |
| Text a **person** reads — UI strings, docs, README | Both, kept in step |
| Public API docstrings — `core/awi.py`, each `awi_mcp.py`, module headers | Both |
| Internal comments explaining why something is the way it is | **Chinese, and that is on purpose** |

That last row is a real decision rather than an omission. Those comments are the
maintainer's thinking, and translating them would flatten what makes them useful. They do
not stop anyone using the project, and the parts you need in order to *extend* it — the
contract, the guidance, the docs — are in both languages.

### Commits

English first, then Chinese, so the history reads as English at a glance:

```text
type: English summary line

English body — what changed and why.

---
中文说明：这次改了什么、为什么这么改。
```

Explain the reasoning, not just the diff. A commit that says *why* is worth more later than
one that restates *what*. `.gitmessage` in the repository root holds this as a template —
`git config commit.template .gitmessage` once per clone and it fills in for you.

## Checklist

- [ ] `pytest -q` passes
- [ ] `ruff check .` passes
- [ ] `python scripts/selfcheck.py` passes
- [ ] `python docs/check_readme.py` passes if you touched a README
- [ ] Behaviour changed → **both** `CHANGELOG.md` and `CHANGELOG_zh.md`, plus the relevant README
- [ ] **A guard you added actually fires.** Break the thing on purpose, watch the test go
      red, put it back. A guard nobody has seen fail is a guard nobody knows works — this
      project has caught four that had silently stopped guarding.

## Real hardware

⚠️ Code and commands that touch real hardware carry physical risk. **Anyone running them
must be present at the machine.** See [SECURITY.md](SECURITY.md).

## Reporting

Open an issue. For anything security-related, read [SECURITY.md](SECURITY.md) first — in
particular §2, on why connecting a world is a trust decision.

Licence: this project is released under [MIT](LICENSE). Contributing means agreeing that
your contribution is offered under MIT as well. MIT already permits closed-source
commercial use, so there is no contributor agreement to sign and no dual-licensing
arrangement. Which terms apply to which release is recorded in [NOTICE](NOTICE).
