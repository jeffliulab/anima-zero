<div align="center">

<a href="SECURITY.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="SECURITY_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

</div>

# Security

> ANIMA Zero is an **open research prototype**, built as a portfolio and teaching project.
> What follows is an honest account of what it does and does not protect against.

## 1. This is a prototype, not a certified system

ANIMA carries no safety certification. **Do not** use it in medical, industrial, automotive
or any other safety-critical setting. Doing so would require verification and certification
you would have to carry out yourself.

## 2. ⭐ Connecting a world is a trust decision

This is the section worth understanding, because it follows from the architecture rather
than from any particular bug.

ANIMA is a **host** in the MCP sense, and a **world** is a separate process reached over a
URL. The authority it hands that world is unusual:

| Channel | Where the world's text ends up |
|---|---|
| **Guidance** | Concatenated into the brain's **system prompt** — the model's highest-authority channel |
| **Tool descriptions** | The model's function-calling tool sheet |
| **Action results** | The conversation history |
| **`kind` / `readOnlyHint`** | Used to decide whether the safety gate ran at all (reclaimed in v1.1, below) |

In other words: **connecting somebody else's world means letting a stranger write into your
brain's system prompt.** This is not a theoretical worry. The industry has names for the two
attacks — **tool poisoning** (description text a server controls enters the agent's context
and is acted on as trusted) and **rug pull** (a server behaves while being reviewed and
changes its descriptions once approved) — along with real incidents and CVEs.

### What we do about it

1. **Approval binds to content, not to a name.** The first time you connect a world, every
   tool it declares (name, kind, description, schema) and its guidance **in full** are put
   in front of you, and you decide. What is recorded is the SHA-256 of that manifest. If it
   has not changed you are not asked again; **if it has, you are asked again and told what
   changed**. This is the same idea as SSH pinning a host key or Docker pinning an image
   digest: substituting something new under an old name has to be detectable.
2. **An unapproved world's content does not reach the brain.** It still lists and still
   reports whether it is online — so you can approve it — but its guidance never enters the
   system prompt and its tools never enter the tool sheet.
3. **Guidance is fenced and labelled before injection.** The model is told the block is
   **material, not instruction**, and that it cannot override the rules above it. The fence
   markers are stripped from the world's own text, so it cannot close the fence early and
   have the rest read as ANIMA's own words. There is also a length cap.
4. **The safety gate was taken back from the world (v1.1).** The orchestrator used to read
   the world's own `kind` to decide whether to consult the gate — so a world could skip it
   entirely by annotating a destructive tool as read-only. **Every world action now goes to
   the gate**, with `kind` as one input to that decision and never a bypass. Harmless while
   the gate is open in simulation; a hole the day it is switched on for real hardware, which
   is the only reason `safety.py` exists.
5. Each of the above is held by a test in `tests/test_world_trust.py`, against a fixture
   that does what a malicious world would actually do.

### What we do **not** do — please read this part

- **Prompt injection is not solved.** Fencing and length caps raise the bar. Nothing
  inspects the guidance for hostile intent, and no such check would be reliable. This is an
  open problem for the entire field.
- **The trust model governs whether to connect, not whether what you are told is true.** An
  approved world can still send fabricated camera frames or report a failed action as a
  success. What the brain sees is what that world chose to show it.
- **So the real protection is you**: read the manifest when you approve it. An approval
  clicked through without reading is not an approval.

### In one line

**Only connect worlds you trust.**

> `ANIMA_TRUST_ALL=1` skips every approval, for development — when you are editing your own
> world, the manifest changes on every save. It belongs on your machine only, never in
> anything shared or published.

## 3. The brain makes mistakes (inherent to LLMs)

ANIMA's decisions come from a large language model, cloud or local, and **it can hallucinate
or judge wrongly**. The design accounts for this: the brain only *thinks* — it selects tools
and fills in arguments — and never holds the logical ground truth. Before anything real
happens there is a safety gate and, where it matters, a human.

## 4. Real hardware

The current version is software only — virtual worlds and physics simulation. It **has
never driven real hardware**. But that is where ANIMA is going, so:

- Real motion carries physical risk. Those commands must be run by someone **present at the
  machine**.
- This is a servo arm: **the emergency stop is cutting power**, and when power is cut the
  joints go limp and drop. Someone has to be holding it.
- Keep the servo gripper angle **≤100°**; beyond that, gear backlash makes it dangerous.
- Check before dispatching: is the action legal, did you actually see clearly, is the grasp
  angle safe? High-risk or irreversible actions need explicit human approval.
- ⚠️ Before real hardware, `src/core/safety.py` must move from `default_allow=True` to
  `False` with real deterministic checks filled in. **Those checks must never exempt an
  action because of the `kind` a world declared** — see §2, point 4.

## 5. Network exposure

The backend serves this machine only by default. Before binding to `0.0.0.0` or setting
`ANIMA_CORS_ORIGINS=*`, be clear about what that means: anyone on the network can create a
session and drive whatever world you have connected. The `*` in `.env.example` is a local
demo convenience, not a deployment default.

## 6. Keys

Model API keys live in a local `.env`, which is gitignored and never committed. Note also
that conversation content goes to whichever model provider you choose — do not paste into a
session anything that must not leave the machine.

## 7. Reporting

Open an issue for anything security-related, or email the maintainer (address in
`pyproject.toml` under `authors`).
