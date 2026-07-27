"""仓库路径的单一来源（禁止硬编码/散落 `__file__+".."` 的收口点）。

本模块恒在 `src/`（= anima 包根）直下，`REPO_ROOT` 只按「src 的上一级」算，与
调用者身处哪个子包无关——所以模块下沉进子包后也不用再数 `..`，一次算对。
本模块不 import 任何 anima 模块，无循环依赖。

- `.cache/`  = 纯机器缓存（pytest / ruff / pycache / build），可随时删。
- `logs/`    = 流水日志（awi / games / 会话流水），大脑跑出来的留痕。
- `memory/`  = 会话记忆（会话记录 + 感知图），单用户本地、不入库。
"""
from __future__ import annotations

import os

_PKG = os.path.dirname(os.path.abspath(__file__))    # .../<repo>/src  == anima 包根
REPO_ROOT = os.path.dirname(_PKG)                     # 仓库根（src 的上一级）
CACHE_DIR = os.path.join(REPO_ROOT, ".cache")         # 纯机器缓存
LOGS_DIR = os.path.join(REPO_ROOT, "logs")            # 流水日志：awi-*/games-*/sessions/
MEMORY_DIR = os.path.join(REPO_ROOT, "memory")        # 会话记忆根（记录 + 图）
SESSIONS_DIR = os.path.join(MEMORY_DIR, "sessions")   # 会话记录 + imgs → memory/sessions
ENV_FILE = os.path.join(REPO_ROOT, ".env")            # 后端/CLI 读的 .env

# ---- 用户级目录（与仓库无关）--------------------------------------------------------
# User-level directory, deliberately NOT derived from the repository.
#
# Everything above is repo-relative, which is right for logs and session memory: they
# belong to a checkout. Trust decisions do not. Someone who installed ANIMA with pip has
# no repository at all, and a decision like "I have reviewed this world and approved it"
# should follow the person, not the working copy — deleting a clone must not silently
# re-trust anything.
#
# 上面那些都是相对仓库的，对日志和会话记忆来说是对的：它们属于某一份 checkout。**信任决定不是。**
# 用 pip 装 ANIMA 的人根本没有仓库；而"我审阅过这个世界并批准了它"这种决定应当跟着**人**走、
# 不跟着工作副本走——删掉一个 clone 绝不该悄悄地把什么东西重新变成可信的。
ANIMA_HOME = os.environ.get("ANIMA_HOME") or os.path.join(os.path.expanduser("~"), ".anima")
TRUST_FILE = os.path.join(ANIMA_HOME, "trust.json")   # 已审批世界的清单哈希（见 core/trust.py）
