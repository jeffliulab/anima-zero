#!/usr/bin/env python3
"""eval —— ANIMA 下棋能力的独立「记分台」（事后读日志评分，不碰主程序）。

⛔ 铁律（你定的）：
- **完全独立**：只读 `logs/`，不 import anima 主程序任何模块，不驱动大脑/世界。单独运行：`python eval/eval_chess.py`。
- 依赖仅 stdlib + `python-chess`（第三方库）+ 一个 UCI 引擎（Stockfish，做评分基准）。

读什么：
- `logs/games-*.jsonl`：世界落的【完整对局】（双方 UCI + 结果 + 谁执子）——算棋力分的来源（T4a 落的档）。
- `logs/awi-*.jsonl`：脑↔世界流量——取每步 `ms` 延迟、`resp.ok` 合法/失败率（与棋谱互补）。
- 也可 `--pgn FILE.pgn` 直接评标准棋谱（无日志时照样能用）。

算什么（主流象棋评分标准）：
- **ACPL**（平均每步丢多少厘兵）—— 棋力金标准；**accuracy%**（lichess 公式，由 ACPL 推）；blunder/mistake/inaccuracy 计数；
  命中最佳着率；**粗略估算 Elo**；ANIMA 视角胜/和/负。需要 UCI 引擎；没装则**如实跳过**这部分（绝不假装能算）。
- 引擎无关：合法率、决策延迟（来自 AWI 日志）、对局数、ANIMA 走子数。

输出：`eval/out/scorecard.json` + `eval/out/scorecard.html` + 终端摘要。

环境变量（都可不设，有默认）：
- EVAL_ENGINE   UCI 引擎路径或名（默认 "stockfish"；找不到则只出引擎无关指标）
- EVAL_DEPTH    引擎分析深度（默认 12）
- EVAL_LOGS_DIR 日志目录（默认 ../logs）
- EVAL_OUT_DIR  输出目录（默认 ./out）
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import math
import os
import statistics
import sys
from pathlib import Path

try:
    import chess
    import chess.engine
    import chess.pgn
except ImportError:
    sys.exit("需要 python-chess：pip install chess（eval 只依赖 stdlib + python-chess + 一个 UCI 引擎）")

_HERE = Path(__file__).resolve().parent
LOGS_DIR = os.getenv("EVAL_LOGS_DIR") or str(_HERE.parent / "logs")
OUT_DIR = os.getenv("EVAL_OUT_DIR") or str(_HERE / "out")
ENGINE_NAME = os.getenv("EVAL_ENGINE", "stockfish")
ENGINE_DEPTH = int(os.getenv("EVAL_DEPTH", "12"))

# lichess 的失误阈值（厘兵）：丢子多少算 失误/错着/大漏着
INACCURACY_CP, MISTAKE_CP, BLUNDER_CP = 50, 100, 300
CP_CAP = 1000          # 单步 CPL 上限（防一个漏着把均值带飞）
MATE_CP = 10000        # 将杀换算成的厘兵分


# ---------------- 读日志 ----------------
def _read_jsonl(path: str) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return out


def load_games_from_logs() -> list[dict]:
    games = []
    for p in sorted(glob.glob(os.path.join(LOGS_DIR, "games-*.jsonl"))):
        for rec in _read_jsonl(p):
            if rec.get("game") == "chess" and rec.get("moves"):
                games.append(rec)
    return games


def load_games_from_pgn(pgn_path: str) -> list[dict]:
    """把标准 PGN 转成与 games 日志同构的记录（白/黑取 PGN 头，anima 默认当白方，可在头里写 [White "anima"]）。"""
    games = []
    with open(pgn_path, encoding="utf-8") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            board = game.board()
            moves = []
            for mv in game.mainline_moves():
                moves.append(mv.uci())
                board.push(mv)
            res = {"1-0": "white", "0-1": "black", "1/2-1/2": "draw"}.get(game.headers.get("Result", "*"), "")
            games.append({"game": "chess", "moves": moves, "result": res,
                          "white": game.headers.get("White", "anima"),
                          "black": game.headers.get("Black", "bot"), "source": "pgn"})
    return games


def awi_move_stats() -> dict:
    """从 AWI 日志取 sim-chess 的 move invoke：合法/失败率 + 决策延迟。与棋谱互补（这边有每步耗时）。"""
    oks, lat = [], []
    for p in sorted(glob.glob(os.path.join(LOGS_DIR, "awi-*.jsonl"))):
        for e in _read_jsonl(p):
            if e.get("world") == "sim-chess" and e.get("method") == "invoke" \
                    and str(e.get("summary", "")).startswith("move("):
                resp = e.get("resp") or {}
                if "ok" in resp:
                    oks.append(1 if resp["ok"] else 0)
                if isinstance(e.get("ms"), (int, float)):
                    lat.append(float(e["ms"]))
    n = len(oks)
    return {
        "move_invokes": n,
        "legal_rate": (sum(oks) / n) if n else None,
        "latency_ms_mean": (statistics.mean(lat) if lat else None),
        "latency_ms_p95": (sorted(lat)[int(0.95 * (len(lat) - 1))] if lat else None),
        "latency_samples": len(lat),
    }


# ---------------- 棋力评分（需 UCI 引擎） ----------------
def _open_engine():
    try:
        return chess.engine.SimpleEngine.popen_uci(ENGINE_NAME)
    except (FileNotFoundError, OSError, chess.engine.EngineError):
        return None


def _cp(score: chess.engine.PovScore, pov: chess.Color) -> int:
    return score.pov(pov).score(mate_score=MATE_CP)


def score_games(games: list[dict], engine) -> dict:
    """逐局复盘，对【anima 控制的那一方】每步算 CPL（vs 引擎最佳）。返回聚合指标。"""
    limit = chess.engine.Limit(depth=ENGINE_DEPTH)
    cpls: list[int] = []
    best_hits = 0
    counts = {"inaccuracy": 0, "mistake": 0, "blunder": 0}
    wdl = {"win": 0, "draw": 0, "loss": 0}
    per_game = []
    for g in games:
        anima_side = "white" if g.get("white") == "anima" else ("black" if g.get("black") == "anima" else None)
        if anima_side is None:
            anima_side = "white"   # PGN / 无标注时默认评白方
        anima_color = chess.WHITE if anima_side == "white" else chess.BLACK
        board = chess.Board()
        g_cpls = []
        for uci in g["moves"]:
            mv = chess.Move.from_uci(uci)
            if board.turn == anima_color and mv in board.legal_moves:
                info = engine.analyse(board, limit)
                best_score = _cp(info["score"], anima_color)
                best_move = info.get("pv", [None])[0]
                board.push(mv)
                after = engine.analyse(board, limit)
                actual_score = _cp(after["score"], anima_color)
                cpl = max(0, min(CP_CAP, best_score - actual_score))
                g_cpls.append(cpl)
                cpls.append(cpl)
                if best_move is not None and mv == best_move:
                    best_hits += 1
                if cpl >= BLUNDER_CP:
                    counts["blunder"] += 1
                elif cpl >= MISTAKE_CP:
                    counts["mistake"] += 1
                elif cpl >= INACCURACY_CP:
                    counts["inaccuracy"] += 1
            else:
                if mv in board.legal_moves:
                    board.push(mv)
                else:
                    break   # 棋谱与规则不符（理论上不会）→ 停止这局
        res = g.get("result")
        if res in ("white", "black"):
            wdl["win" if res == anima_side else "loss"] += 1
        elif res == "draw":
            wdl["draw"] += 1
        per_game.append({"anima_side": anima_side, "moves_scored": len(g_cpls),
                         "acpl": round(statistics.mean(g_cpls), 1) if g_cpls else None})
    n = len(cpls)
    acpl = statistics.mean(cpls) if n else None
    return {
        "scored_moves": n,
        "acpl": round(acpl, 1) if acpl is not None else None,
        "accuracy_pct": _accuracy_from_acpl(acpl) if acpl is not None else None,
        "best_move_match_pct": round(100 * best_hits / n, 1) if n else None,
        "blunders": counts["blunder"], "mistakes": counts["mistake"], "inaccuracies": counts["inaccuracy"],
        "est_elo": _rough_elo(acpl) if acpl is not None else None,
        "result_wdl": wdl,
        "per_game": per_game,
    }


def _accuracy_from_acpl(acpl: float) -> float:
    """lichess 公布的 accuracy↔ACPL 经验公式（粗略），夹到 0–100。"""
    return round(max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * acpl) - 3.1669)), 1)


def _rough_elo(acpl: float) -> int:
    """ACPL→Elo 的【粗略】估算（仅作量级参考，非官方等级分）。"""
    return int(max(400, 3000 * math.exp(-0.01 * acpl)))


# ---------------- 输出 ----------------
def render_html(report: dict) -> str:
    s, a = report["summary"], report["awi"]
    sc = report.get("strength")
    rows = []

    def row(k, v):
        rows.append(f"<tr><td>{html.escape(k)}</td><td><b>{html.escape(str(v))}</b></td></tr>")

    row("对局数 (games)", s["games"])
    row("ANIMA 走子数 (scored moves)", s["scored_moves"])
    row("合法率 legal-rate", f'{a["legal_rate"]*100:.1f}%' if a["legal_rate"] is not None else "—")
    row("决策延迟 mean / p95 (ms)",
        f'{a["latency_ms_mean"]:.0f} / {a["latency_ms_p95"]:.0f}' if a["latency_ms_mean"] is not None else "—")
    if sc:
        row("ACPL（平均每步丢厘兵·越低越强）", sc["acpl"])
        row("accuracy %（lichess 公式）", sc["accuracy_pct"])
        row("命中最佳着率", f'{sc["best_move_match_pct"]}%' if sc["best_move_match_pct"] is not None else "—")
        row("大漏/错着/小失误 (blunder/mistake/inaccuracy)",
            f'{sc["blunders"]} / {sc["mistakes"]} / {sc["inaccuracies"]}')
        row("粗略估算 Elo（量级参考，非官方）", sc["est_elo"])
        w = sc["result_wdl"]
        row("ANIMA 视角 胜/和/负", f'{w["win"]} / {w["draw"]} / {w["loss"]}')
    note = "" if sc else ('<p style="color:#b00">⚠️ 未找到 UCI 引擎，已跳过棋力分（ACPL/Elo）。'
                          '装 Stockfish 后重跑：<code>apt install stockfish</code> 或设 <code>EVAL_ENGINE=/path/to/engine</code>。</p>')
    return f"""<!doctype html><meta charset="utf-8"><title>ANIMA 下棋记分卡</title>
<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:40px auto;color:#222">
<h1>ANIMA 下棋记分卡</h1>
<p style="color:#666">独立 eval · 读 <code>logs/games-*.jsonl</code> + <code>logs/awi-*.jsonl</code> · 引擎：{html.escape(report["engine"])}</p>
{note}
<table style="border-collapse:collapse;width:100%">
<style>td{{border:1px solid #ddd;padding:8px 12px}}</style>{''.join(rows)}</table>
<p style="color:#999;font-size:12px">ACPL=平均每步比引擎最佳少走的厘兵；accuracy/Elo 为经验换算，仅供量级参考。</p>
</body>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="ANIMA 下棋记分台（独立读日志评分）")
    ap.add_argument("--pgn", help="改读标准 PGN 文件（不读 games 日志）")
    args = ap.parse_args()

    games = load_games_from_pgn(args.pgn) if args.pgn else load_games_from_logs()
    awi = awi_move_stats()

    report = {"engine": "(none)", "summary": {"games": len(games), "scored_moves": 0}, "awi": awi, "strength": None}

    if not games:
        print(f"没找到对局记录（{LOGS_DIR}/games-*.jsonl 为空）。先下几盘棋让世界落档，或用 --pgn 指定棋谱。")
    else:
        engine = _open_engine()
        if engine is None:
            print(f"⚠️ 未找到 UCI 引擎 '{ENGINE_NAME}'，只出引擎无关指标（合法率/延迟/对局数）。"
                  f"装 Stockfish 后可得 ACPL/Elo：apt install stockfish 或设 EVAL_ENGINE。")
        else:
            try:
                strength = score_games(games, engine)
            finally:
                engine.quit()
            report["engine"] = ENGINE_NAME
            report["strength"] = strength
            report["summary"]["scored_moves"] = strength["scored_moves"]

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "scorecard.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "scorecard.html"), "w", encoding="utf-8") as f:
        f.write(render_html(report))

    # 终端摘要
    s, a, sc = report["summary"], report["awi"], report["strength"]
    print(f"\n=== ANIMA 下棋记分卡 ===")
    print(f"对局 {s['games']} · ANIMA 走子 {s['scored_moves']} · 引擎 {report['engine']}")
    if a["legal_rate"] is not None:
        print(f"合法率 {a['legal_rate']*100:.1f}% · 延迟均值 {a['latency_ms_mean']:.0f}ms（{a['latency_samples']} 步）")
    if sc:
        print(f"ACPL {sc['acpl']} · accuracy {sc['accuracy_pct']}% · 命中最佳着 {sc['best_move_match_pct']}% "
              f"· 漏/错/小 {sc['blunders']}/{sc['mistakes']}/{sc['inaccuracies']} · ≈Elo {sc['est_elo']}")
        w = sc["result_wdl"]
        print(f"ANIMA 视角 胜/和/负 {w['win']}/{w['draw']}/{w['loss']}")
    print(f"→ 报告：{os.path.join(OUT_DIR, 'scorecard.html')} / scorecard.json")


if __name__ == "__main__":
    main()
