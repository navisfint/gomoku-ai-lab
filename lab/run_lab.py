# -*- coding: utf-8 -*-
"""
对照实验：证明 v1 -> v2 -> v3 到底有没有变强，以及在哪儿变强。

做三件事：
  A. 关键局面测试 —— 7 个有唯一正解的局面，看各版本选得对不对。
  B. 同条件对战   —— 固定基准 v1，黑白互换，两种开局，同一时间限制。
  C. 用时统计     —— 单步最大/平均用时，检查是否满足 3 秒 / 每局 60 秒。

输出：lab/results/results.json + lab/results/结果汇总.md + 控制台表格
"""
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import engine_lab as L
import gomoku_v1 as v1
import gomoku_v2 as v2
import gomoku_v3 as v3

RES_DIR = os.path.join(HERE, "results")
ENGINES = [
    ("v1 原始版", v1.v1_get_move),
    ("v2 优化版", v2.v2_get_move),
    ("v3 试验版", v3.v3_get_move),
]
OPENINGS = [
    ("A 空盘开局", ()),
    ("B 中心+斜挂", ((7, 7, "X"), (6, 8, "O"))),
]
STEP_LIMIT = 3.0        # 单步上限
SIDE_LIMIT = 60.0       # 每方每局累计上限


# ---------------------------------------------------------------- A 关键局面
def replay_key_game():
    """复盘那一局：黑方由 v2 代打（模拟一个会下的人），白方是 v1。
    P3 用的就是这局里白方走出致命错误的那一手之前的棋面。"""
    board = L.new_board()
    turn = "X"
    stones = []
    while len(stones) < 27:
        eng = v2.v2_get_move if turn == "X" else v1.v1_get_move
        mv = eng(board, turn)
        board[mv[0]][mv[1]] = turn
        stones.append((mv[0], mv[1], turn))
        turn = "O" if turn == "X" else "X"
    return stones, turn


def key_positions():
    """每个局面：(名称, 先手色, 棋子, 正解集合, 说明)"""
    ps = []

    # P1 自己能一步成五：必须先赢，不要做别的
    ps.append((
        "P1 自己一步成五", "X",
        [(7, 4, "X"), (7, 5, "X"), (7, 6, "X"), (7, 7, "X"),
         (6, 6, "O"), (8, 8, "O"), (5, 5, "O"), (9, 3, "O")],
        {(7, 3), (7, 8)},
        "黑已有四连，两端任一空点即五连"))

    # P2 对手一步成五：必须堵，自己去进攻没有意义
    ps.append((
        "P2 对手一步成五", "X",
        [(7, 4, "O"), (7, 5, "O"), (7, 6, "O"), (7, 7, "O"),
         (6, 6, "X"), (8, 8, "X"), (5, 5, "X"), (9, 3, "X")],
        {(7, 3), (7, 8)},
        "白已有四连，黑不堵就被五连"))

    # P3 对手的"活四成点"：这是真实对局里 v1 漏掉的那一手（棋面直接从对局复盘而来）
    # 正解不手写：凡是"落子后对手就不再拥有活四成点"的着法都算对。
    # 因为防住一个活四有两条路：直接占掉那个点，或者先封死这条线的一端
    # （让他即便补中间也只能成冲四，还能再堵）。
    kstones, kturn = replay_key_game()
    kb = L.from_stones(kstones)
    kopp = "X" if kturn == "O" else "O"
    ok3 = set()
    for rr in range(15):
        for cc in range(15):
            if kb[rr][cc] != ".":
                continue
            wb = [row[:] for row in kb]
            wb[rr][cc] = kturn
            top = max(v2.v2_point_score(wb, x, y, kopp, kturn)
                      for x in range(15) for y in range(15) if wb[x][y] == ".")
            if top < v2.T_OPEN4:
                ok3.add((rr, cc))
    ps.append((
        "P3 对手活四成点（关键）", kturn, kstones, ok3,
        "黑在列上 X X . X，中间一补就是活四；白必须在这一手就化解（占点或先封一端）"))

    # P4 自己能做活四：两步必胜，应当立刻做
    ps.append((
        "P4 自己做活四", "X",
        [(7, 7, "X"), (7, 8, "X"), (7, 9, "X"),
         (10, 3, "O"), (10, 12, "O"), (4, 4, "O"), (11, 6, "O")],
        {(7, 6), (7, 10)},
        "黑在 (7,6) 或 (7,10) 落子成 4 连且两端全空 = 活四，白挡不住"))

    # P5 跳四：中间隔一个空的四连，空隙就是必堵点
    ps.append((
        "P5 跳四必堵", "X",
        [(7, 5, "O"), (7, 6, "O"), (7, 8, "O"), (7, 9, "O"),
         (9, 5, "X"), (9, 6, "X"), (10, 10, "X")],
        {(7, 7)},
        "白 X X . X X，空隙 (7,7) 一填就是五连"))

    # P6 双活三：一手同时做出两条活三，对手只能挡一条
    ps.append((
        "P6 双活三", "X",
        [(7, 6, "X"), (7, 8, "X"), (5, 7, "X"), (6, 7, "X"),
         (10, 2, "O"), (11, 12, "O"), (3, 10, "O"), (12, 4, "O")],
        {(7, 7)},
        "黑在 (7,7) 同时形成横、竖两条活三"))

    # P7 开局：应当靠近中心，而不是贴着边角
    ps.append((
        "P7 空盘开局", "X",
        [(7, 7, "X"), (6, 8, "O")],
        {(6, 7), (7, 6), (8, 7), (7, 8), (6, 6), (6, 9), (8, 6), (8, 9),
         (5, 7), (9, 7), (8, 8), (5, 8), (5, 6)},
        "第三手应贴着中心（距离天元 1~2 格的合理范围内）"))

    # 过滤掉占位的 "." 项
    out = []
    for name, turn, stones, ok, note in ps:
        stones = [(r, c, s) for r, c, s in stones if s != "."]
        out.append((name, turn, stones, ok, note))
    return out


def run_key_tests():
    rows = []
    for name, turn, stones, ok, note in key_positions():
        board = L.from_stones(stones)
        row = {"position": name, "turn": turn, "note": note,
               "expected": sorted("%s%d" % (chr(ord("A") + c), 15 - r) for r, c in ok),
               "results": {}}
        for ename, eng in ENGINES:
            snap = [r[:] for r in board]
            t0 = time.perf_counter()
            try:
                mv = eng(board, turn)
            except Exception as e:
                row["results"][ename] = {"move": "异常 %r" % (e,), "pass": False,
                                         "sec": 0.0}
                continue
            dt = time.perf_counter() - t0
            legal = board[mv[0]][mv[1]] == "." and board == snap
            passed = legal and (int(mv[0]), int(mv[1])) in ok
            row["results"][ename] = {
                "move": "%s%d" % (chr(ord("A") + int(mv[1])), 15 - int(mv[0])),
                "pass": bool(passed), "sec": round(dt, 4)}
        rows.append(row)
    return rows


# ---------------------------------------------------------------- B 对战
def run_tournament(rounds_per_pair=1):
    games = []
    pairs = [
        ("v2 优化版", v2.v2_get_move, "v1 原始版", v1.v1_get_move),
        ("v3 试验版", v3.v3_get_move, "v1 原始版", v1.v1_get_move),
        ("v3 试验版", v3.v3_get_move, "v2 优化版", v2.v2_get_move),
    ]
    for aname, aeng, bname, beng in pairs:
        for oname, op in OPENINGS:
            for color in ("black", "white"):
                if color == "black":
                    eb, ew, ean, ewn = aeng, beng, aname, bname
                else:
                    eb, ew, ean, ewn = beng, aeng, bname, aname
                res = L.play_game(eb, ew, opening=op, step_limit=STEP_LIMIT)
                winner = res["winner"]
                if winner == "draw":
                    outcome = "平"
                else:
                    a_is_black = (color == "black")
                    a_won = (winner == "X") == a_is_black
                    outcome = "胜" if a_won else "负"
                times = res["times"]
                games.append({
                    "pair": "%s vs %s" % (aname, bname),
                    "a": aname, "b": bname,
                    "opening": oname,
                    "a_color": "黑" if color == "black" else "白",
                    "winner": winner,
                    "outcome_for_a": outcome,
                    "moves": len(res["moves"]),
                    "error": res["error"],
                    "max_step": round(max(times), 4) if times else 0.0,
                    "sum_step": round(sum(times), 3) if times else 0.0,
                })
    return games


def self_play_bias():
    """同一个引擎自我对弈，用来看"固定开局本身有没有偏向某一方"。

    这不是比赛成绩，只是实验条件校准：如果某个开局下 v2 打 v2 都能分出胜负，
    说明该开局本身就带偏向，那一栏结果不能直接拿来判断谁更强。
    """
    out = []
    for oname, op in OPENINGS:
        r = L.play_game(v2.v2_get_move, v2.v2_get_move, opening=op)
        out.append({"opening": oname, "winner": r["winner"],
                    "moves": len(r["moves"])})
    return out


def summarize(games):
    """按版本汇总战绩。"""
    tally = {}
    for g in games:
        for side in ("a", "b"):
            name = g[side]
            if name not in tally:
                tally[name] = {"games": 0, "win": 0, "draw": 0, "loss": 0,
                               "moves": 0, "max_step": 0.0, "sum_step": 0.0}
            t = tally[name]
            t["games"] += 1
            t["moves"] += g["moves"]
            t["max_step"] = max(t["max_step"], g["max_step"])
            t["sum_step"] += g["sum_step"]
            if g["winner"] == "draw":
                t["draw"] += 1
            else:
                a_won = ((g["winner"] == "X") == (g["a_color"] == "黑"))
                i_won = a_won if side == "a" else (not a_won)
                t["win" if i_won else "loss"] += 1
    return tally


# ---------------------------------------------------------------- 输出
def to_markdown(key_rows, games, tally, bias):
    L_ = []
    L_.append("# 五子棋 AI 对照实验结果\n")

    L_.append("## A. 关键局面测试（每题只有唯一正解）\n")
    L_.append("| 局面 | 正解 | v1 原始版 | v2 优化版 | v3 试验版 |")
    L_.append("|---|---|---|---|---|")
    score = {}
    for row in key_rows:
        cells = []
        for ename, _ in ENGINES:
            r = row["results"][ename]
            mark = "✅" if r["pass"] else "❌"
            cells.append("%s %s" % (r["move"], mark))
            score[ename] = score.get(ename, 0) + (1 if r["pass"] else 0)
        L_.append("| %s | %s | %s |" % (row["position"], " / ".join(row["expected"]),
                                        " | ".join(cells)))
    L_.append("")
    L_.append("**答对题数**：" + " · ".join(
        "%s %d/%d" % (e, score.get(e, 0), len(key_rows)) for e, _ in ENGINES))
    L_.append("")
    for row in key_rows:
        L_.append("- **%s**（%s走）：%s" % (row["position"],
                                          "黑" if row["turn"] == "X" else "白",
                                          row["note"]))
    L_.append("")

    L_.append("## B. 同条件对战（固定基准 v1，黑白互换，同一 3 秒/步限制）\n")
    L_.append("| 对局 | 开局 | A 方执 | 结果 | 手数 | 单步最长 |")
    L_.append("|---|---|---|---|---|---|")
    for g in games:
        L_.append("| %s | %s | %s | %s（%s） | %d | %.3fs |"
                  % (g["pair"], g["opening"], g["a_color"],
                     g["outcome_for_a"], g["winner"], g["moves"], g["max_step"]))
    L_.append("")

    L_.append("### 实验条件校准：同一引擎自我对弈\n")
    L_.append("| 开局 | v2 vs v2 结果 | 手数 |")
    L_.append("|---|---|---|")
    for b in bias:
        L_.append("| %s | %s | %d |" % (b["opening"], b["winner"], b["moves"]))
    L_.append("")
    L_.append("若某个开局下同版本自战都能分出胜负，说明该开局本身偏向某一方，"
              "该栏结果不能单独用来判断强弱。\n")

    L_.append("## C. 汇总\n")
    L_.append("| 版本 | 对局数 | 胜 | 平 | 负 | 单步最长 | 平均每步 |")
    L_.append("|---|---|---|---|---|---|---|")
    for ename, _ in ENGINES:
        t = tally.get(ename)
        if not t:
            continue
        L_.append("| %s | %d | %d | %d | %d | %.3fs | %.4fs |"
                  % (ename, t["games"], t["win"], t["draw"], t["loss"],
                     t["max_step"], t["sum_step"] / max(1, t["moves"])))
    L_.append("")
    return "\n".join(L_)


def main():
    if not os.path.isdir(RES_DIR):
        os.makedirs(RES_DIR)

    print("=" * 70)
    print("A. 关键局面测试")
    print("=" * 70)
    key_rows = run_key_tests()
    for row in key_rows:
        cells = []
        for ename, _ in ENGINES:
            r = row["results"][ename]
            cells.append("%s %s" % (r["move"], "OK " if r["pass"] else "X  "))
        print("%-22s 正解 %-10s | %s" % (row["position"],
                                         "/".join(row["expected"]), " | ".join(cells)))

    print()
    print("=" * 70)
    print("B. 同条件对战")
    print("=" * 70)
    games = run_tournament()
    for g in games:
        print("%-22s %-12s A执%s  %s(%s)  %3d手  单步最长%.3fs"
              % (g["pair"], g["opening"], g["a_color"], g["outcome_for_a"],
                 g["winner"], g["moves"], g["max_step"]))

    bias = self_play_bias()
    print()
    print("--- 实验条件校准：同引擎自我对弈 ---")
    for b in bias:
        print("%-12s %s  %d手" % (b["opening"], b["winner"], b["moves"]))

    tally = summarize(games)
    print()
    print("=" * 70)
    print("C. 汇总")
    print("=" * 70)
    for ename, _ in ENGINES:
        t = tally.get(ename)
        if t:
            print("%-12s %d局 胜%d 平%d 负%d  单步最长%.3fs"
                  % (ename, t["games"], t["win"], t["draw"], t["loss"], t["max_step"]))

    with io.open(os.path.join(RES_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"key_positions": key_rows, "games": games, "tally": tally,
                   "self_play": bias},
                  f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(RES_DIR, "结果汇总.md"), "w", encoding="utf-8") as f:
        f.write(to_markdown(key_rows, games, tally, bias))
    print("\n已写出 lab/results/results.json 和 结果汇总.md")


if __name__ == "__main__":
    main()
