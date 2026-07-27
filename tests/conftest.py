"""pytest 公共夹具 / 路径。

`anima` 包已可直接 import（pyproject 把 src/ 映射成 anima）。
`world/sim-chess/render.py` 是"世界"进程的渲染器、不是 anima 包的一部分，
但视觉 round-trip 测试要用它当"摄像头画面"的真实来源，所以把它所在目录加进 sys.path。
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SIM_CHESS = os.path.join(_HERE, "..", "world", "sim-chess")
if _SIM_CHESS not in sys.path:
    sys.path.insert(0, os.path.abspath(_SIM_CHESS))

# ---------------------------------------------------------------------------------------
# Cut the developer's `.env` out of the test run — at module scope, because the leak
# happens at import time, before any fixture can run.
#
# `presentation/server.py` calls `load_dotenv(paths.ENV_FILE)` when it is imported, which
# copies the developer's local configuration into `os.environ` for the whole process. Any
# test that imports the backend, directly or through something else, then runs against
# whatever that person happens to have configured.
#
# That was invisible for as long as `.env` only held API keys and addresses. It stopped
# being invisible the moment it held a variable that changes behaviour: adding
# `ANIMA_TRUST_ALL=1` for local development made five security tests pass for the wrong
# reason — they were asserting that an unapproved world is refused, and it was being
# allowed. Tests that quietly agree with whatever is on the machine are worse than no
# tests, so the file is taken out of reach entirely.
#
# 把开发者的 `.env` 从测试运行里切出去——放在模块层，因为泄漏发生在 **import 时**，
# 早于任何夹具能运行的时刻。
#
# `presentation/server.py` 在被 import 时会 `load_dotenv(paths.ENV_FILE)`，把开发者的本地配置
# 灌进整个进程的 `os.environ`。于是任何直接或间接 import 后端的测试，跑的都是**那个人碰巧配了什么**。
#
# 只要 `.env` 里放的还只是 API key 和地址，这件事就一直看不见。它不再看不见，是在 `.env` 里出现了
# 一个**会改变行为**的变量那一刻：为本地开发加上 `ANIMA_TRUST_ALL=1` 之后，五条安全测试开始
# **因为错误的原因通过**——它们断言的是"未批准的世界会被拒绝"，而实际发生的是它被放行了。
# 一个会默默附和本机配置的测试套件，比没有测试更糟，所以干脆把这个文件拿到够不着的地方。
from anima import paths  # noqa: E402

paths.ENV_FILE = os.path.join(_HERE, "this-env-file-does-not-exist")


@pytest.fixture(autouse=True)
def _isolated_anima_home(tmp_path, monkeypatch):
    """Point `ANIMA_HOME` at a throwaway directory for every test.

    The trust store lives outside the repository, in the user's home — which is correct in
    production and unacceptable in a test run: a suite that writes there could approve a
    world on the developer's real machine, or read an approval they made by hand and pass
    for the wrong reason. Both are silent. Isolating it once here is cheaper than
    remembering to isolate it in each test.

    每个测试的 `ANIMA_HOME` 都指向一个用完就扔的目录。

    信任存储住在仓库之外的用户主目录里——这在生产上是对的，在测试里则不可接受：一个往那儿写的测试
    套件可能在开发者的**真实机器上批准一个世界**，也可能读到他手工批过的记录、于是**因为错误的
    原因通过**。两种都是静默的。在这里隔离一次，比每个测试都记得隔离要便宜。
    """
    monkeypatch.setenv("ANIMA_HOME", str(tmp_path / "anima-home"))
