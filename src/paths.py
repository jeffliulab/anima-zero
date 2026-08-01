"""路径的单一来源（禁止硬编码/散落 `__file__+".."` 的收口点）。

本模块恒在 `src/`（= anima 包根）直下，`REPO_ROOT` 只按「src 的上一级」算，与
调用者身处哪个子包无关——所以模块下沉进子包后也不用再数 `..`，一次算对。
本模块不 import 任何 anima 模块，无循环依赖。

- `.cache/`  = 纯机器缓存（pytest / ruff / pycache / build），可随时删。
- `logs/`    = 流水日志（awi / games / 会话流水），大脑跑出来的留痕。
- `memory/`  = 会话记忆（会话记录 + 感知图），单用户本地、不入库。

⭐ 这些东西**落在哪儿，取决于你是怎么装的**——见下面 `_IN_CHECKOUT`。
"""
from __future__ import annotations

import os

_PKG = os.path.dirname(os.path.abspath(__file__))    # .../<repo>/src  == anima 包根
REPO_ROOT = os.path.dirname(_PKG)                     # 源码检出里 = 仓库根（src 的上一级）

# ---- 用户级目录（与仓库无关）--------------------------------------------------------
# User-level directory, deliberately NOT derived from the repository.
#
# A decision like "I have reviewed this world and approved it" should follow the person,
# not the working copy — deleting a clone must not silently re-trust anything. Someone who
# installed ANIMA with pip has no repository at all, so this is also the only place their
# data can live.
#
# "我审阅过这个世界并批准了它"这种决定应当跟着**人**走、不跟着工作副本走——删掉一个 clone
# 绝不该悄悄地把什么东西重新变成可信的。而用 pip 装 ANIMA 的人根本没有仓库，所以这里也是
# 他的数据唯一能落的地方。
ANIMA_HOME = os.environ.get("ANIMA_HOME") or os.path.join(os.path.expanduser("~"), ".anima")
TRUST_FILE = os.path.join(ANIMA_HOME, "trust.json")   # 已审批世界的清单哈希（见 core/trust.py）

# ---- 我是跑在源码检出里，还是被 pip 装进了 site-packages？----------------------------
#
# It decides where logs, session memory and .env live, and the two answers are both right:
#
#   · In a checkout, `REPO_ROOT` really is the repository. Logs and sessions belong to that
#     working copy (they are what you just produced while developing it), and `.env` sitting
#     next to the code is what every contributor expects.
#   · Installed from a wheel, `REPO_ROOT` is **site-packages**. Writing there is wrong in
#     every way that matters: the data is wiped by the next upgrade, it may not even be
#     writable, and `.env` — the file the README tells a new user to create — would have to
#     be placed inside the virtualenv's innards, which nobody would ever find.
#
# The signal is `pyproject.toml` next to the package: present in a clone and in an editable
# install (`pip install -e`, where the code is still the repository), absent in a wheel.
#
# ⚠️ v1.2 之前只有信任库（上面 TRUST_FILE）走了 ANIMA_HOME，日志/记忆/.env 没跟上——于是
#    pip 用户的日志被写进 site-packages，而且**他根本没有地方写 .env**、配不了 API key。
#    独立审计在干净 venv 里实测到这条（demo 结尾打印的就是 site-packages 里的路径）。
#    判据是"包旁边有没有 pyproject.toml"：clone 和 `pip install -e` 都有（那时候代码本来
#    就还是仓库），wheel 装出来的没有。
_IN_CHECKOUT = os.path.isfile(os.path.join(REPO_ROOT, "pyproject.toml"))

# 数据根：检出里 = 仓库根（老行为，贡献者零感知）；装出来的 = ~/.anima（跟着人走）。
DATA_ROOT = REPO_ROOT if _IN_CHECKOUT else ANIMA_HOME

CACHE_DIR = os.path.join(DATA_ROOT, ".cache")         # 纯机器缓存
LOGS_DIR = os.path.join(DATA_ROOT, "logs")            # 流水日志：awi-*/games-*/sessions/
MEMORY_DIR = os.path.join(DATA_ROOT, "memory")        # 会话记忆根（记录 + 图）
SESSIONS_DIR = os.path.join(MEMORY_DIR, "sessions")   # 会话记录 + imgs → memory/sessions
ENV_FILE = os.path.join(DATA_ROOT, ".env")            # 后端/CLI 读的 .env
