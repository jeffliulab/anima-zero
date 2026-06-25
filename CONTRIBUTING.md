# Contributing to ANIMA

Thanks for thinking about contributing. This is an **alpha solo-maintainer** project; a few ground rules will make collaboration smoother.

## Before you start

- Open an issue (bug or feature) **before** opening a PR for anything non-trivial. This saves wasted work.
- Read [`docs/00-overview.md`](./docs/00-overview.md) and the design invariants listed there. Changes that break the invariants need explicit discussion.
- Read the [Code of Conduct](./CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/jeffliulab/anima-zero.git
cd anima-zero
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

Run tests:
```bash
pytest
```

Run linters / formatters:
```bash
ruff check .
ruff format .
```

## Branching and commits

- Branch from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `refactor/<topic>`.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
  - Scopes (project-specific): `l0`, `l1`, `l2`, `l3`, `l4`, `l5`, `testcheck`, `llm`, `docs`.
  - Example: `feat(l1): support DeepSeek provider via LLM_PROVIDER env var`.

## Pull requests

- Keep PRs focused: one PR = one logical change. Split refactors from feature work.
- Tests required for any behavior change in `src/`.
- Docs updates required when adding/removing public API or changing user-visible behavior.
- For safety-critical changes (new adapters, force envelopes, gate thresholds), describe the impact in the PR body.

## What we will and won't accept

**Welcomed:**
- Bug fixes with a regression test
- Documentation fixes and clarifications
- New `L4` adapters (wheelchair, manipulator, mobile base, etc.) following the `EmbodiedAdapter` protocol
- New skill base classes in `l3_skill.py`
- New LLM provider adapters implementing the `LLMToolCaller` protocol

**Not accepted without prior discussion:**
- Changes to the six-layer architecture
- Changes to the five-factor assessment semantics (especially multiplicative GOA)
- Weakening of Test-and-Check gates
- Dependencies with non-permissive licenses (we are Apache 2.0)

## Application-specific code

Domain-specific skills (move a chess piece, grasp a cup) do **not** belong in this repo. They live in the application repository that depends on ANIMA — for example [`soma-zero`](https://github.com/jeffliulab/soma-zero), the live body for VLA chess.

## Release process

- SemVer. Alpha is `0.x.y`.
- Releases driven by [`CHANGELOG.md`](./CHANGELOG.md) using Keep-a-Changelog format.
- Breaking changes flagged with `!` in the Conventional Commit.

## Questions

Open a GitHub Discussion (once enabled) or email the maintainer at the address listed in `pyproject.toml`.
