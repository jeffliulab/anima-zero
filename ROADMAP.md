<div align="center">

<a href="ROADMAP.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="ROADMAP_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# Roadmap

This is not a wish list. It is the mirror of what the CHANGELOG already admits does not
work, plus the debts taken on deliberately, each with a number so it can be pointed at.

A roadmap of features nobody has started is marketing. A roadmap of measured failures is a
plan.

## Maturity

What you can rely on, stated plainly.

| Part | Maturity | What that means |
|---|---|---|
| AWI contract | **Stable** | Additions only within v1; a breaking change gets a new major version |
| Brain core (orchestrator, session, LLM adapters) | **Beta** | Works, and the internals still move between releases |
| Trust model | **Beta** | The rules are settled; the surfaces around them are not |
| The worlds | **Experimental** | Each exists to test one thing, and is rewritten when that thing changes |

**This is a research prototype, not a production framework.** It has no security
certification and has never driven real hardware. See [SECURITY.md](SECURITY.md).

## Open targets

### R1 · Room identification is confirmation-biased

Five target rooms, one run each: two correct, two wrong, one unfinished. Measured in v1.0
and unchanged since.

The interesting part is what it is *not*. The suspicion was that a kitchen and a bathroom
look alike from 0.38 m, which is part of why the humanoid was added — but at 1.25 m it sees
the hob and the range hood clearly and still calls it a bathroom. Facing the same doorway,
the model composes whatever story fits the room it is currently hunting for.

Aimed at the acceptance criterion rather than at perception: describe first and classify
second, and tighten what "I can see it, so I have arrived" is allowed to mean.

### R2 · The prompt language switch has not been measured

v1.1 rewrote every prompt the model reads from Chinese into English — the system prompt,
the tool descriptions, the state blocks, and the worlds' guidance.

**That is a behaviour change, and the benchmark that would settle it has not been re-run.**
The reasoning is in `src/prompts.py`: instruction-tuned models are trained predominantly on
English, and a Chinese prompt wrapped around English tool schemas is a mixed context. The
measured effect in the literature is small, a few percent, and occasionally negative.

Owed: the same five rooms, before and after, side by side. Until that exists, "English is
better here" is a hypothesis, not a result. If it turns out worse, the rollback point is
one file.

### R3 · Prompt injection is mitigated, not solved

A world's guidance is fenced and labelled as material rather than instruction, and capped
in length. That raises the bar. Nothing inspects it for hostile intent, and no such check
would be reliable — this is open for the whole field.

The protection that works is the human approval in `anima world add`, and it only works if
the person actually reads the manifest. See [SECURITY.md](SECURITY.md) §2.

### R4 · Four high-severity CVEs in the frontend's npm tree

`next`, `postcss`, `sharp` and `@tailwindcss/postcss`, all fixable in range. They are
build-time and none reaches the browser bundle, but they are real and they are known.

Not yet done because a Next major bump needs the interface checked by eye, which is a
separate piece of work from the release.

### R5 · The chess rules library is fast enough, not fast

`packages/anima-chess` is two to four times slower than python-chess depending on the
position — enough for the depth-3 advisory search it exists to serve (1.27 s against a
1.5 s cap), and not enough for anything deeper.

The known cost is that the Zobrist hash is rebuilt from scratch on every push rather than
updated incrementally. That is documented in `push()` as a deliberate choice, and it is the
first thing to change when a transposition table arrives.

### R6 · Chinese still reaches a few surfaces

The v1.1 language pass moved everything a model reads, and everything the CLI and web app
show, into English. Four places were left, each for a reason:

- `src/worlds/desk/awi_mcp.py` — MCP resource and prompt descriptions. This file exists as a
  **byte-identical copy in six places**, one of them a submodule, held by a test. Changing
  four strings means changing all six in lockstep, which is not a thing to do on release day.
- `src/dev_turn.py` — a development harness, not a shipped command.
- `src/config.py` field descriptions and two orchestrator log lines — internal only. The
  panel hints they used to feed are now separate and English.

Found by installing the wheel and running it, not by reading the source. The scan that found
them is worth keeping: walk the AST, collect string constants that are not docstrings, and
look for CJK.

## Not planned

Saying no is part of a roadmap.

- **Chess960, PGN, opening books, UCI** in `anima-chess` — use python-chess, which is
  better at all of them.
- **A curl installer.** ANIMA is Python and its worlds are Python; the people who would run
  it already have Python. `uv tool install` gives the same one-command experience without a
  second distribution channel to keep honest.
- **Making the brain smarter about any specific world.** Task-specific knowledge lives in
  the world. The moment the orchestrator learns what chess is, the framework claim is over.
