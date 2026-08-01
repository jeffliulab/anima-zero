"""随包网页的整页路由：直接打开不许 404。

StaticFiles(html=True) 只会给目录找 index.html，不会把 /awi 映射到 awi.html——于是
直接打开 /awi、/session-logs 曾经 404（应用内跳转是客户端路由，从不经过这里，
这个毛病只在「直接打开链接」时现形，而文档恰恰让人直接打开它们）。
"""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def test_full_pages_are_served_at_their_routes(tmp_path, monkeypatch):
    from anima.presentation import server

    web = tmp_path / "web"
    web.mkdir()
    for page in ("index", "awi", "session-logs", "anima-logs"):
        (web / f"{page}.html").write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setattr(server, "_UI_DIR", str(web))
    # 路由在模块 import 时按 _UI_DIR 注册——换掉目录后必须 reload 才按新目录重挂。
    srv = importlib.reload(server)
    try:
        client = TestClient(srv.app)
        for page in ("", "awi", "session-logs", "anima-logs"):
            r = client.get(f"/{page}")
            assert r.status_code == 200, f"/{page} 直接打开是 {r.status_code}，不是 200"
    finally:
        monkeypatch.undo()
        importlib.reload(server)    # 还原成真实目录的挂载，别把一个临时目录留给后面的测试
