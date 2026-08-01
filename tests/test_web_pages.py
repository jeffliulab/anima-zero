"""随包网页的整页路由：直接打开不许 404。

StaticFiles(html=True) 只会给目录找 index.html，不会把 /awi 映射到 awi.html——于是
直接打开 /awi、/session-logs 曾经 404（应用内跳转是客户端路由，从不经过这里，
这个毛病只在「直接打开链接」时现形，而文档恰恰让人直接打开它们）。

⛔ 这里**不依赖本机构建过界面**：`src/presentation/web/` 是构建产物、不入库，CI 的
   Python job 根本不构建它。测试自己造一个临时目录当界面，交给 `mount_ui` 挂到一个全新的
   app 上。上一版靠 monkeypatch 常量 + reload 模块来换目录，而 reload 会把常量重新赋回
   真路径——于是它实际测的是开发者本机碰巧构建过的那份，在 CI 里则直接红。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from anima.presentation import server


def _app_with_ui(tmp_path):
    """一个全新的 app + 一个临时「界面目录」，内容由测试自己写。"""
    web = tmp_path / "web"
    web.mkdir()
    for page in ("index", *server._FULL_PAGES):
        (web / f"{page}.html").write_text(f"<html>{page}</html>", encoding="utf-8")
    app = FastAPI()
    assert server.mount_ui(app, str(web)) is True
    return TestClient(app)


def test_full_pages_are_served_at_their_routes(tmp_path):
    client = _app_with_ui(tmp_path)
    for page in server._FULL_PAGES:
        r = client.get(f"/{page}")
        assert r.status_code == 200, f"/{page} 直接打开是 {r.status_code}，不是 200"
        assert page in r.text, f"/{page} 端出来的不是它自己那张页面"


def test_the_index_still_comes_from_the_static_mount(tmp_path):
    """整页路由是**加**在通配挂载前面的，不是替掉它——根路径照旧走 StaticFiles。"""
    client = _app_with_ui(tmp_path)
    r = client.get("/")
    assert r.status_code == 200 and "index" in r.text


def test_no_ui_directory_mounts_nothing_and_says_so(tmp_path):
    """源码检出里没跑过 build_ui.py 是**正常状态**，不是故障：安静地不挂载。"""
    app = FastAPI()
    assert server.mount_ui(app, str(tmp_path / "never-built")) is False
    assert TestClient(app).get("/").status_code == 404
