# sim-chess

<a href="README.md"><img src="https://img.shields.io/badge/Language-English-2f81f7?style=flat-square" alt="English"></a>
<a href="README_zh.md"><img src="https://img.shields.io/badge/%E8%AF%AD%E8%A8%80-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-e67e22?style=flat-square" alt="简体中文"></a>

A standalone **world** (AWI) for ANIMA: a **simulated board with a built-in player**. It runs
human-vs-computer on its own, and either side can be handed to ANIMA.

**The brain gets pixels and nothing else.** Perception (MCP `resources/read
anima://observation`) returns one frame and an **empty state `{}`** — since the v0.4
simplification even `controllers` and `phase` are gone, and no ground truth of any kind is
given. There is a separate out-of-band `/stream` (MJPEG) for people to watch. **The board's
structured truth — the position, a FEN — is never handed over.** The brain has to look. The
outcome of a command is expressed as `ok` (success/fail) on the MCP `tools/call`.

Any two of three roles can play each other: each side's controller is `human`, `anima` or
`bot`.

```
# The rules come from anima-chess in this repo (MIT). It is not on PyPI yet, so install it
# once from the working tree.
pip install -e ../../packages/anima-chess
cd world/sim-chess && pip install -e . && uvicorn server:app --port 8102
```

Open `localhost:8102`: pick the controller for each side, then start. On a human side, click
the square a piece is on and then the square it goes to.
