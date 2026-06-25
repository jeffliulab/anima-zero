# 00 · Overview

> Reading map for the `anima` cognitive framework.

## How to read this folder

1. **Start with the original IP** — `preserved/anima-public-readme.md`, then `preserved/10-ANIMA认知框架设计.md`.
   These define the philosophy, five-layer architecture, five-factor assessment, and Test-and-Check validation that this framework is built on.

2. **Read the in-repo source as the living spec.**
   - [`src/anima/l0_signal.py`](../src/anima/l0_signal.py) — upstream signal layer (BCI / ASR / vision / text)
   - [`src/anima/l1_parser.py`](../src/anima/l1_parser.py) — LLM-as-Parser with forced tool-calling
   - [`src/anima/l2_planner.py`](../src/anima/l2_planner.py) — TaskSpec → behavior tree
   - [`src/anima/l3_skill.py`](../src/anima/l3_skill.py) — skill registry + executor base classes
   - [`src/anima/l4_adapter.py`](../src/anima/l4_adapter.py) — device-agnostic actuation layer
   - [`src/anima/l5_assessment.py`](../src/anima/l5_assessment.py) — ITA / MQA / SQA / GOA / PEA
   - [`src/anima/test_and_check.py`](../src/anima/test_and_check.py) — six-gate validation before execution
   - [`src/anima/taskspec.py`](../src/anima/taskspec.py) — Pydantic schemas

3. **See the reference application** that exercises this framework end-to-end:
   - [`soma-zero`](https://github.com/jeffliulab/soma-zero) — the body for VLA chess (perception + arm execution); pairs with this brain
   - _Archived predecessors:_ [`ARCHIVE_soma-arm`](https://github.com/jeffliulab/ARCHIVE_soma-arm) (old O1 chess arm), [`ARCHIVE_soma-care`](https://github.com/jeffliulab/ARCHIVE_soma-care) (medical-care sim, kept as a capstone seed)

## Design invariants (do not change)

1. **LLM-as-Parser, not LLM-as-Generator.** The LLM produces structured TaskSpec JSON. It does not directly emit motor commands.
2. **Test-and-Check before execution.** Six gates: JSON / intent / skill / params / safety / preconditions.
3. **Five-factor event-triggered self-assessment.** ITA / MQA / SQA / GOA / PEA.
4. **Three-stage time evaluation.** Pre / Runtime / Post — orthogonal to the five factors.
5. **GOA composition is multiplicative.** `P(success) = ∏ P_i`. No false confidence from averaging.
6. **PEA retrieval is three-factor.** `recency × 0.5 + relevance × 3.0 + importance × 2.0`.
7. **Behavior-tree runtime.** No ad-hoc state machines.
8. **Function-Calling + Affordance Scoring instead of RAG** when skill set < 100.

## What this framework provides

| Layer | Role |
|---|---|
| **L0 Signal** | Upstream input (BCI, speech, vision, text). Produces intent tokens with confidence and drift metadata. |
| **L1 Parser** | LLM-as-Parser with forced tool-calling. Emits a validated TaskSpec. |
| **L2 Planner** | TaskSpec → py_trees BehaviorTree. Order-preserving; reasoning lives in L1. |
| **L3 Skill** | Function-Calling + Affordance Scoring over a registry of skill classes. |
| **L4 Adapter** | Device-agnostic actuation — same L1–L3 targets manipulators, mobile bases, wheelchairs, humanoids. |
| **L5 Assessment** | Five-factor event-triggered assessment at Pre / Runtime / Post stages. |

## Out of scope

- Building actual neural decoders / ASR / VLA models — the framework defines the interface; applications slot in real models.
- Domain-specific skills (grasp a cup, move a chess piece, wipe a patient). These live in the application repo, not here.
- Regulatory submissions, EHR integration, hospital data pipelines — downstream of applications, not of the framework.
