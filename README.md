# ANIMA Zero

**ANIMA** = **A**utonomous **N**atural-language **I**nstruction **M**apping **A**rchitecture.

**ANIMA Zero** is the open-source line of the ANIMA cognitive framework — the *brain* that
decides what to do, paired with [`soma-zero`](https://github.com/jeffliulab/soma-zero), the
*body* that senses and acts. This Zero line is fully open source; deeper production work
continues in private repos.

A domain-agnostic cognitive framework for intent-to-action embodied AI. It turns an upstream signal (BCI, speech, vision, text) into a validated, executable task on any device that implements the adapter protocol.

## The idea in one paragraph

Most embodied-AI stacks either (a) let an LLM emit motor commands directly, which is unsafe and unauditable, or (b) bolt a rigid state machine onto a planner, which does not generalise. ANIMA splits the problem into six layers and five assessment factors: the LLM is used strictly as a **parser** that emits a structured `TaskSpec`, a six-gate **Test-and-Check** rejects unsafe specs before execution, a **behavior tree** runs the plan with tick-level observability, and a **five-factor self-assessment** (ITA/MQA/SQA/GOA/PEA) attaches a probability of success to every decision. The stack is deliberately device-agnostic — the same L1–L3 drives a manipulator, a mobile base, a wheelchair, or a future humanoid through a pluggable L4 adapter.

## Architecture

```
  upstream signal (BCI / ASR / vision / text)
                 │
                 ▼
       ┌──────────────────┐
       │ L0  Signal        │  signal → intent token + confidence + drift
       └────────┬─────────┘
                ▼
       ┌──────────────────┐
       │ L1  Parser (LLM)  │  instruction → TaskSpec (forced tool-calling)
       └────────┬─────────┘
                ▼
       ┌──────────────────┐
       │ Test-and-Check    │  6 gates: JSON/intent/skill/params/safety/preconds
       └────────┬─────────┘
                ▼
       ┌──────────────────┐
       │ L2  Planner       │  TaskSpec → py_trees BehaviorTree
       └────────┬─────────┘
                ▼
       ┌──────────────────┐
       │ L3  Skill         │  Function-Calling + Affordance Scoring
       └────────┬─────────┘
                ▼
       ┌──────────────────┐
       │ L4  Adapter       │  device-agnostic actuation (arm / base / ...)
       └────────┬─────────┘
                ▼
       ┌──────────────────┐
       │ L5  Assessment    │  ITA · MQA · SQA · GOA · PEA (Pre/Runtime/Post)
       └──────────────────┘
```

### Design invariants

1. **LLM-as-Parser, not LLM-as-Generator.** The LLM emits structured `TaskSpec` JSON via forced tool-calling. It never emits motor commands.
2. **Test-and-Check before execution.** Six gates reject malformed or unsafe specs.
3. **Five-factor event-triggered self-assessment.** Not continuous logging.
4. **Three-stage time evaluation.** Pre / Runtime / Post — orthogonal to the five factors.
5. **GOA composition is multiplicative.** `P(success) = ∏ Pᵢ`. Averaging is forbidden because it masks low-probability bottlenecks.
6. **PEA retrieval is three-factor.** `recency × 0.5 + relevance × 3.0 + importance × 2.0`.
7. **Behavior-tree runtime.** No ad-hoc state machines.
8. **Function-Calling + Affordance Scoring instead of RAG** when the skill set is < 100 entries.

## Quick start

```bash
git clone https://github.com/jeffliulab/anima-zero.git
cd anima-zero
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

Ticking a trivial plan end-to-end with the built-in mocks:

```python
import asyncio
from anima import TaskSpec, IntentToken, Subtask, Constraints
from anima.l2_planner import build_tree, run_tree

spec = TaskSpec(
    intent=IntentToken(token="DRINK_WATER", confidence=0.9,
                       drift_score=0.05, source_text="I want some water"),
    subtasks=[
        Subtask(name="locate_cup", type="locate"),
        Subtask(name="grasp_cup",  type="grasp"),
        Subtask(name="lift_cup",   type="lift"),
    ],
    constraints=Constraints(max_force_n=8.0, timeout_s=15.0),
)

tree = build_tree(spec, skill_registry={})  # empty → MockSkillBehaviour
status = asyncio.run(run_tree(tree, tick_interval_s=0.01))
print(status)  # Status.SUCCESS
```

## Reference applications

ANIMA is the brain; the body that exercises it lives in a separate repo.

| Application | Repo | What it does |
|---|---|---|
| **SOMA Zero** | [jeffliulab/soma-zero](https://github.com/jeffliulab/soma-zero) | **Live.** The body for VLA chess — perception (camera → board state) + arm execution (pick-and-place). The reference application this brain pairs with. |
| _SOMA Arm_ | [ARCHIVE_soma-arm](https://github.com/jeffliulab/ARCHIVE_soma-arm) | _Archived._ Old O1 tabletop chess arm; superseded by SOMA Zero. |
| _SOMA Care_ | [ARCHIVE_soma-care](https://github.com/jeffliulab/ARCHIVE_soma-care) | _Archived._ Medical-care hospital-ward sim; kept as a capstone seed. |

Domain-specific skills (move a chess piece, grasp a cup) live in the application repo, not here. ANIMA itself ships only the framework, the mocks, and the tests.

## Status

**Alpha (0.1.x).** First reference implementation landed 2026-04-21 (absorbed from the `anima-intention-action` BCI application branch). Renamed from `anima` (internally "ANIMA O1") to **`anima-zero`** on 2026-06-25 — the Zero line continues development from this v0.1 base. APIs may still change prior to `1.0.0`; breaking changes will be flagged with `!` in the commit message and called out in [`CHANGELOG.md`](./CHANGELOG.md).

Design docs live under [`docs/`](./docs/). The original Anima IP (Chinese, more abstract) is preserved verbatim in [`docs/preserved/`](./docs/preserved/) for provenance.

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Jeff Liu Lab ([jeffliulab.com](https://jeffliulab.com), GitHub [@jeffliulab](https://github.com/jeffliulab)).

You may use, modify, and redistribute this code commercially or privately, provided you keep the copyright and license notices and document any changes you make. Contributors grant an explicit patent license; suing a contributor over patents in this work terminates your license.
