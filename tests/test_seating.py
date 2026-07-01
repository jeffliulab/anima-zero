"""sim-chess 简化后（v0.4）：世界对大脑**只暴露 move**、perceive 只给画面（state 空）、**无开局仪式**；
+ 对弈 skill 的 launcher「按 role 起树、不碰世界」。纯 Python、无 HTTP、确定性。

背景：旧的「选边就座 / 配对手 / 点开始 / phase 三阶段 / controllers」整套已撤——那是把简单事搞复杂了、
也是通用大脑绕过下棋技能乱点仪式工具的诱因。现在轮到谁走由 python-chess 走子合法性天然管；对手（人/内置电脑）
是世界自己网页上的事（bot_side），不对大脑暴露。
"""
from __future__ import annotations

from types import SimpleNamespace

from anima.awi import Capabilities, Observation, ToolSpec
from anima.skills.boardgame import _play_launch, _record_launch, build_registry
from world import SimChessWorld   # conftest 把 world/sim-chess 加进了 sys.path


# ---------- 1) 简化后的世界本体 ----------
def test_capabilities_only_move_no_ceremony():
    caps = SimChessWorld().capabilities()
    names = {t["name"] for t in caps["tools"]}
    assert names == {"move"}, "对大脑只有 move（take_seat/seat_opponent/start_game/resign 已撤）"
    assert caps["state_schema"] == {}, "perceive 不声明任何结构化真值"


def test_observe_state_empty():
    state, png = SimChessWorld().observe()
    assert state == {} and png, "只给画面；state 空，绝不夹带局面/轮次/胜负"


def test_move_works_without_ceremony():
    w = SimChessWorld()
    assert w.invoke("move", **{"from": "e2", "to": "e4"})["ok"], "无需选边/开局，直接就能走合法着"


def test_move_illegal_and_turn_by_legality():
    w = SimChessWorld()
    assert w.invoke("move", **{"from": "e2", "to": "e5"})["ok"] is False, "白兵一步越两格越子不合法"
    w.invoke("move", **{"from": "e2", "to": "e4"})          # 轮到黑
    assert w.invoke("move", **{"from": "d2", "to": "d4"})["ok"] is False, "没轮到白（黑回合）→ 白手不合法"


def test_ceremony_gone_inside_and_out():
    w = SimChessWorld()
    assert w.invoke("take_seat", seat="white")["ok"] is False, "旧仪式工具对大脑已不存在（未知能力）"
    for attr in ("phase", "controllers", "set_controller", "take_seat", "start_game", "seat_opponent"):
        assert not hasattr(w, attr), f"内部也去掉了 {attr}"


def test_bot_side_and_human_click_guard():
    w = SimChessWorld()
    assert w.set_bot_side("black")["bot_side"] == "black", "网页配内置电脑走黑"
    assert w.human_click_move("e2", "e4")["ok"], "白回合、白非内置电脑 → 人可点子走"
    assert w.human_click_move("e7", "e5")["ok"] is False, "现在轮到黑（=内置电脑），人不能替它走"


# ---------- 2) launcher：按 role 起树，不碰世界 ----------
class _FakeWorld:
    """把 perceive/invoke/capabilities 代理到真 SimChessWorld，让 launcher 跑在真实世界上（无 HTTP；runner 不 tick）。"""
    name = "fw"
    base = "fake://fw"

    def __init__(self):
        self.w = SimChessWorld()

    def capabilities(self):
        d = self.w.capabilities()
        tools = [ToolSpec(t["name"], t["description"], t["parameters"], t.get("kind", "tool")) for t in d["tools"]]
        return Capabilities(d["name"], d.get("version", ""), tools=tools)

    def perceive(self):
        state, _png = self.w.observe()
        return Observation(image_png=None, state=state)

    def invoke(self, name, **args):
        r = self.w.invoke(name, **args)
        return SimpleNamespace(ok=r.get("ok", False), message=r.get("message", ""), data=r.get("data", {}))

    def close(self):
        pass


def _close(res):
    try:
        res["runner"].bb.world.close()
    except Exception:
        pass


def test_play_launch_with_role_starts_tree_without_touching_world():
    """给 role=white 就起对弈树；launcher 不 take_seat/start_game（那套已没了），也不替你动世界棋盘。"""
    fw = _FakeWorld()
    res = _play_launch(build_registry().get("chess"), fw, llm=None, role="white")
    try:
        assert res["ok"] and res["my_side"] == "white" and "runner" in res
        assert not fw.w.board.move_stack, "launcher 只起树，不替你走子/开局"
    finally:
        _close(res)


def test_play_launch_without_role_asks_side():
    """没给 role → 如实问执哪方（绝不默认选边），不起 runner。"""
    fw = _FakeWorld()
    res = _play_launch(build_registry().get("chess"), fw, llm=None, role=None)
    assert res["ok"] is False and "哪一方" in res["message"] and "runner" not in res


def test_record_launch_starts_runner():
    """记录棋盘 sub-skill：进入即起一个读盘 runner（不需要 role）。"""
    fw = _FakeWorld()
    res = _record_launch(build_registry().get("chess_record"), fw, llm=None)
    try:
        assert res["ok"] and "runner" in res
    finally:
        _close(res)


def test_family_launchable_by_capability_not_by_name():
    """下棋家族靠【能力查询】挂载：play/record 需 move（sim-chess 有）→ 挂得上；
    setup 需 place（sim-chess 没有）→ 挂不上（只在物理世界可用，不靠世界名特判）。"""
    reg = build_registry()
    assert reg.get("chess_setup").required_action == "place"
    sim_tools = {t.name for t in _FakeWorld().capabilities().tools}
    assert "place" not in sim_tools and "move" in sim_tools
    launchable = {s.id for s in reg.launchable_on(_FakeWorld())}
    assert {"chess", "chess_record"} <= launchable
    assert "chess_setup" not in launchable, "sim-chess 没 place → 摆盘挂不上"
