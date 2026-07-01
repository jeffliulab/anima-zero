"""「选边就座」机制 + 对弈 launcher「一步到位」测试（Wave 7）。

座位机制 = 普通工具 `take_seat`（不再有单独的 claim/seats 声明，那套已删）。两层：
1. sim-chess 世界本体（纯 Python，无 HTTP）：take_seat 选边、约束、start_game 需配齐、perceive 只给 {controllers, phase}。
2. 对弈 skill 的 launcher：按大脑给的 role 自动就座 + 配齐就开局 + 起行为树；已坐则幂等读旧座；
   没给 role 又没坐则如实问执哪方；对手没配齐则进面板空转等。
"""
from __future__ import annotations

from types import SimpleNamespace

from anima.awi import Capabilities, Observation, ToolSpec
from anima.skills.boardgame import _play_launch, _record_launch, build_registry
from world import SimChessWorld   # conftest 把 world/sim-chess 加进了 sys.path


# ---------- 1) 世界本体：选边 + 状态机 ----------
def test_capabilities_declares_seat_verbs_only():
    caps = SimChessWorld().capabilities()
    assert "seats" not in caps, "不再单独声明 seats（claim 机制已删，座位靠 take_seat 工具）"
    names = {t["name"] for t in caps["tools"]}
    assert names == {"take_seat", "seat_opponent", "start_game", "move", "resign"}, \
        "三阶段工具集（无 pause/resume）；seat_opponent = ANIMA 给对手配座"


def test_seat_opponent_seats_the_other_side():
    """ANIMA take_seat 后，seat_opponent(human) 把另一席配成人；接着能 start_game 进比赛中。"""
    w = SimChessWorld()
    w.take_seat("black")
    r = w.seat_opponent("human")
    assert r["ok"] and w.controllers["white"] == "human", "对手配到 anima 没坐的那一席（白）"
    assert w.controllers["black"] == "anima", "自己那席不动"
    assert w.start_game()["ok"] and w.phase == "in_game", "双方配齐 → 可开局"


def test_seat_opponent_requires_taking_seat_first():
    w = SimChessWorld()
    r = w.seat_opponent("bot")
    assert r["ok"] is False and "take_seat" in r["message"], "没就座就配对手 → 拒绝并提示先就座"
    assert w.controllers == {"white": None, "black": None}, "拒绝时不动任何席位"


def test_seat_opponent_rejects_invalid_who():
    w = SimChessWorld()
    w.take_seat("white")
    assert w.seat_opponent("anima")["ok"] is False, "对手不能配成 anima（那是自己）"
    assert w.seat_opponent("空")["ok"] is False, "对手不能配成空"


def test_take_seat_picks_side_and_anima_only_once():
    w = SimChessWorld()
    assert w.controllers == {"white": None, "black": None}, "席位默认空（世界不预设）"
    r = w.take_seat("white")
    assert r["ok"] and w.controllers["white"] == "anima"
    bad = w.take_seat("black")
    assert bad["ok"] is False and "anima 只能占一方" in bad["message"]


def test_take_seat_rejects_occupied_seat():
    w = SimChessWorld()
    w.set_controller("white", "human")
    r = w.take_seat("white")
    assert r["ok"] is False and "已被" in r["message"]


def test_take_seat_unknown_seat():
    r = SimChessWorld().take_seat("purple")
    assert r["ok"] is False and "席位" in r["message"]


def test_start_game_needs_both_seats():
    w = SimChessWorld()
    w.take_seat("white")
    assert w.start_game()["ok"] is False, "缺对手席位不能开始"
    w.set_controller("black", "bot")
    assert w.start_game()["ok"] and w.phase == "in_game"


def test_observe_state_is_controllers_and_phase_only():
    w = SimChessWorld()
    state, png = w.observe()
    assert set(state.keys()) == {"controllers", "phase"}, "perceive 只给角色 meta + phase，绝不夹带局面真值"
    assert state["phase"] == "not_start" and png


# ---------- 2) launcher：一步到位（自动就座 + 配齐就开局 + 幂等） ----------
class _FakeWorld:
    """faithful 假世界：把 perceive/invoke/capabilities 代理到真的 SimChessWorld，
    让 launcher 的自动就座/开局逻辑跑在真实状态机上（无 HTTP；runner 创建后不 tick）。"""
    name = "fw"
    base = "fake://fw"

    def __init__(self, controllers=None, start=False):
        self.w = SimChessWorld()
        for seat, who in (controllers or {}).items():
            if who:
                self.w.set_controller(seat, who)
        if start:
            self.w.start_game()

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


def test_play_launch_with_role_starts_tree_without_ceremony():
    """新框架：给 role=white 就起对弈树；launcher 【不再】take_seat/start_game——
    世界座位/开局是人在世界自己界面上做的（这就是 Jeff 要的「把开局仪式解耦出对弈」）。"""
    fw = _FakeWorld({})                       # 两席全空、not_start
    res = _play_launch(build_registry().get("chess"), fw, llm=None, role="white")
    try:
        assert res["ok"] and res["my_side"] == "white" and "runner" in res
        assert fw.w.controllers == {"white": None, "black": None}, "launcher 不碰世界座位"
        assert fw.w.phase == "not_start", "launcher 不 start_game"
    finally:
        _close(res)


def test_play_launch_without_role_asks_side():
    """没给 role → 如实问执哪方（绝不默认选边），不起 runner。"""
    fw = _FakeWorld({})
    res = _play_launch(build_registry().get("chess"), fw, llm=None, role=None)
    assert res["ok"] is False and "哪一方" in res["message"] and "runner" not in res


def test_record_launch_starts_runner():
    """记录棋盘 sub-skill：进入即起一个读盘 runner（不需要 role）。"""
    fw = _FakeWorld({})
    res = _record_launch(build_registry().get("chess_record"), fw, llm=None)
    try:
        assert res["ok"] and "runner" in res
    finally:
        _close(res)


def test_family_launchable_by_capability_not_by_name():
    """下棋家族靠【能力查询】挂载：play/record 需 move（sim-chess 有）→ 挂得上；
    setup 需 place（sim-chess 没有）→ 挂不上。证明 setup 只在物理世界可用，且不靠世界名特判。"""
    reg = build_registry()
    assert reg.get("chess_setup").required_action == "place"
    sim_tools = {t.name for t in _FakeWorld({}).capabilities().tools}
    assert "place" not in sim_tools and "move" in sim_tools
    launchable = {s.id for s in reg.launchable_on(_FakeWorld({}))}
    assert {"chess", "chess_record"} <= launchable
    assert "chess_setup" not in launchable, "sim-chess 没 place → 摆盘挂不上"
