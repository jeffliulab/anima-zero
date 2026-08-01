"""数据落在哪儿：源码检出 vs pip 装出来的包。

⛔ 这条守的是一个**在开发机上永远看不见**的失效：在检出里 `REPO_ROOT` 就是仓库，一切正常；
   而 wheel 装出来的 `REPO_ROOT` 是 site-packages，往那儿写日志会被下次升级抹掉、可能根本
   没有写权限，更要命的是 `.env`——README 让新用户建的那个文件——会落进 venv 的内脏里，
   没有人找得到，等于 pip 用户**配不了 API key**。v1.2 发版前的独立审计在干净 venv 里实测到。

判据是「包旁边有没有 pyproject.toml」：clone 有、`pip install -e` 有（那时代码还是仓库）、
wheel 装出来的没有。这里用 importlib 在两种假布局下各重算一次 paths 来验。
"""
from __future__ import annotations

import importlib
import sys


def _paths_rooted_at(tmp_path, monkeypatch, *, with_pyproject: bool, anima_home, tag="a"):
    """把 anima.paths 在一个假的包位置上重新算一遍，返回 (重算后的模块, 那个假仓库根)。

    `paths` 用 `__file__` 推 REPO_ROOT，所以这里造一个 <root>/src/paths.py 的假布局，
    让它自己去推——而不是替它算好答案再断言（那样只会验证测试自己）。
    `tag` 让同一个测试里可以造多份互不干扰的布局。
    """
    root = tmp_path / f"layout-{tag}"
    src = root / "src"
    src.mkdir(parents=True)
    real = importlib.import_module("anima.paths")
    with open(real.__file__, encoding="utf-8") as fh:
        (src / "paths.py").write_text(fh.read(), encoding="utf-8")
    if with_pyproject:
        (root / "pyproject.toml").write_text("[project]\nname='fake'\n", encoding="utf-8")

    monkeypatch.setenv("ANIMA_HOME", str(anima_home))
    monkeypatch.syspath_prepend(str(src))
    sys.modules.pop("paths", None)
    mod = importlib.import_module("paths")
    sys.modules.pop("paths", None)
    return mod, root


def test_a_source_checkout_keeps_its_data_in_the_repository(tmp_path, monkeypatch):
    """检出里行为一个字都不变——贡献者的 logs/ memory/ .env 还在仓库根。"""
    home = tmp_path / "home-anima"
    p, root = _paths_rooted_at(tmp_path, monkeypatch, with_pyproject=True, anima_home=home)
    assert p.DATA_ROOT == str(root)
    assert p.LOGS_DIR == str(root / "logs")
    assert p.MEMORY_DIR == str(root / "memory")
    assert p.ENV_FILE == str(root / ".env")


def test_an_installed_package_keeps_its_data_in_anima_home(tmp_path, monkeypatch):
    """⛔ 装出来的包绝不往 site-packages 里写：日志、记忆、.env 全落 ANIMA_HOME。"""
    home = tmp_path / "home-anima"
    p, root = _paths_rooted_at(tmp_path, monkeypatch, with_pyproject=False, anima_home=home)
    assert p.DATA_ROOT == str(home)
    for path in (p.LOGS_DIR, p.MEMORY_DIR, p.SESSIONS_DIR, p.ENV_FILE, p.CACHE_DIR):
        assert path.startswith(str(home)), f"{path} 落在了 ANIMA_HOME 外面"
        assert not path.startswith(str(root)), f"{path} 还落在包目录里"


def test_trust_follows_the_person_in_both_layouts(tmp_path, monkeypatch):
    """信任库从来就跟着人走（v1.1 起），两种布局下都必须还在 ANIMA_HOME。"""
    home = tmp_path / "home-anima"
    for tag, with_pyproject in (("checkout", True), ("installed", False)):
        p, _ = _paths_rooted_at(tmp_path, monkeypatch, with_pyproject=with_pyproject,
                                anima_home=home, tag=tag)
        assert p.TRUST_FILE == str(home / "trust.json")
