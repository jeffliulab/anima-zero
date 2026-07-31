# FAQ / Troubleshooting

<a href="faq.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="faq_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

The six things a new user actually trips over, each as **symptom → cause → what to do**.
When in doubt, `anima doctor` is the first command to run — it exists for exactly this.

## 1. I installed anima-zero and there is no world at all

**Symptom**: `anima world list` shows nothing; `anima doctor` says the list is empty.

**Cause**: normal. Since v1.1.1 the wheel carries the brain only — a world is a separate
program and none ships inside the package.

**What to do**: run `anima demo` first — it starts a small bundled world (a dot on an
eight-cell corridor) and runs one real turn, so you can watch the whole loop work. Then
get a real world: clone the repository for the ones in `world/`, or write your own
against [the AWI spec](awi-spec-v1.md) (`src/examples/minimal_world.py` is the
template).

## 2. My world shows as "offline"

**Symptom**: `anima world list` says `offline` next to your world.

**Cause**: worlds are separate processes — the brain does not start them, it only
connects to ones already running. Either the world is not started, or it is listening
on a different address than the one registered.

**What to do**: start the world first (each world's README has its one-line start
command, e.g. `cd world/sim-chess && uvicorn server:app --port 8102`), then check the
address matches: the world's own log line prints its port, and `ANIMA_WORLDS` in your
`.env` must point at the same one. `curl http://localhost:<port>/health` should answer
`{"ok":true}`.

## 3. The brain refuses to use my world ("not approved")

**Symptom**: the world is online but the brain behaves as if it has no tools; `doctor`
says "not approved — the brain cannot use it".

**Cause**: this is the trust model working as designed, not a bug. A world's tool
descriptions and guidance are text somebody else wrote, and they land in the brain's
system prompt — so nothing reaches the brain until a person has read the manifest and
approved it. See [SECURITY.md](../SECURITY.md) §2.

**What to do**: run `anima world add NAME URL` — it prints everything the world
declares and asks you to decide. Approving binds to the content: if the world comes
back changed, you are asked again. While developing your own world,
`ANIMA_TRUST_ALL=1` skips this (development only).

## 4. I have no API key — can I still try it?

**Symptom**: every brain in `anima doctor` shows "not configured".

**What to do**, three free paths:
- `anima demo` — offers to pull **Qwen3-4B-Instruct-2507** via Ollama (~2.5 GB, runs
  purely on CPU). It really thinks; this is the intended keyless path.
- For the full web app with eyes: install [Ollama](https://ollama.com/download), then
  `ollama pull qwen3-vl:8b` and pick `qwen3-vl` in the brain dropdown.
- The **mock brain** needs nothing at all — but it does not think; it only walks the
  chain so you can watch the plumbing. It says so in every reply.

## 5. "Address already in use" when starting something

**Symptom**: a world or `anima serve` fails with a port-in-use error.

**Cause**: another copy is already running — most often a world left over from an
earlier session.

**What to do**: find who holds the port with `lsof -i :<port>` and stop it, or start
the new one on a different port (every world's server takes `--port`, and the address
lives in `ANIMA_WORLDS`, not in the brain).

## 6. sim-house-nav cannot find its scenes or robots

**Symptom**: the navigation world fails to start, complaining about missing assets.

**Cause**: scenes and robot models come from the companion repository
[alice-house](https://github.com/jeffliulab/alice-house). By default the world looks
for it next to your anima-zero checkout.

**What to do**: clone alice-house next to anima-zero, or point at it from anywhere with
`HOUSENAV_ASSETS_ROOT=/path/to/alice-house`.
