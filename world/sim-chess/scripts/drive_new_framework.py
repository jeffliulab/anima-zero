"""W5 泛化测：用【新框架】的对弈树驱动【真·sim-chess HTTP 世界】，含真实视觉读盘 + 对手(bot)检测。
sim-chess 世界文件没动(仍有 take_seat/start_game 仪式)；这里用它自己的人类页端点(/set_controller,/start)
把局配好(模拟人在网页上操作)，然后新框架只 perceive+move、靠信念判轮次/终局——证明框架不碰仪式也能跑通。"""
import sys, time, httpx
from anima.behavior.trees import boardgame
from anima.tools.boardgame.chess import ChessAdapter
from anima.world_client import RemoteWorld

BASE = "http://localhost:8102"

# 1) 模拟"人在 sim-chess 网页上"配座+开始（这一步不经大脑框架）
c = httpx.Client(timeout=5.0)
c.post(f"{BASE}/reset")
c.post(f"{BASE}/set_controller", json={"seat": "white", "controller": "anima"})
c.post(f"{BASE}/set_controller", json={"seat": "black", "controller": "bot"})
r = c.post(f"{BASE}/start")
print("setup /start ->", r.json())

# 2) 新框架：RemoteWorld + adapter + 从画面 seed 信念（不调 take_seat/start_game）
world = RemoteWorld("sim-chess", BASE)
adapter = ChessAdapter()
prims = {t.name for t in world.capabilities().tools}
print("world prims:", sorted(prims))
obs = world.perceive()
belief = adapter.seed_from_vision(obs.image_png, "white")
print("seeded belief fen:", belief.fen(), "| pieces:", len(belief.piece_map()))

bb = boardgame.BoardGameBlackboard(
    world=world, adapter=adapter, belief=belief, my_side="white", prims=prims,
    narrate=lambda uci, san, st: f"走了 {san}", display_name="Chess Mode")
tree = boardgame.build_boardgame_tree(bb)

# 3) 手动逐拍 tick（配合 server 端 bot 每 ~1s 走一步 + 视觉多帧确认）
anima_moves, opp_moves = 0, 0
for i in range(60):
    tree.tick_once()
    ch = bb.events[-1]["channel"] if bb.events else ""
    if bb.finished:
        print(f"[tick {i}] finished: {bb.exit_reason}")
        break
    time.sleep(0.4)
    if bb.move_count > anima_moves:
        anima_moves = bb.move_count
        print(f"[tick {i}] ANIMA 走了第 {anima_moves} 手  (last={bb.last_uci} {bb.last_san})")
    cur_opp = sum(1 for e in bb.events if e["channel"] == "opponent")
    if cur_opp > opp_moves:
        opp_moves = cur_opp
        print(f"[tick {i}] 视觉认出对手第 {opp_moves} 手")

print("\n=== W5 结果 ===")
print("ANIMA 走子数:", bb.move_count, "| 视觉认出对手走子数:", opp_moves)
print("世界真值 /status:", httpx.get(f"{BASE}/status", timeout=5).json().get("fen", "?"))
ok = bb.move_count >= 2 and opp_moves >= 1
print("PASS" if ok else "FAIL", "—— 新框架在真 sim-chess 上：ANIMA 连走 + 视觉认出对手" )
sys.exit(0 if ok else 1)
