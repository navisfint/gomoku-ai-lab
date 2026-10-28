# -*- coding: utf-8 -*-
"""
AI 引擎接口自测：逐条检查引擎是否满足对外的接口约定（不修改输入棋盘、返回值合法、单步限时等）。

对着生成的 gomoku_v2.py 跑，输出一张通过/不通过的表。
"""
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import engine_lab as L

SUB = (os.path.abspath(sys.argv[1]) if len(sys.argv) > 1
       else os.path.join(ROOT, "gomoku_v2.py"))
N = 15


def load(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("candidate_ai", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(results, name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("%s %-28s %s" % ("[通过]" if ok else "[失败]", name, detail))


def main():
    results = []
    print("被测文件：%s" % SUB)
    print("-" * 72)

    # 1 文件本身
    size = os.path.getsize(SUB)
    with io.open(SUB, "rb") as f:
        raw = f.read()
    utf8_ok = True
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        utf8_ok = False
    check(results, "UTF-8 编码 / 小于 256KB", utf8_ok and size < 256 * 1024,
          "%.1f KB" % (size / 1024.0))

    check(results, "Python 语法正确",
          subprocess.call([sys.executable, "-m", "py_compile", SUB]) == 0)

    # 2 导入不弹窗、无副作用
    code = "\n".join([
        "import importlib.util, sys, time, threading",
        "t = time.time()",
        "spec = importlib.util.spec_from_file_location('m', %r)" % SUB,
        "m = importlib.util.module_from_spec(spec)",
        "spec.loader.exec_module(m)",
        "assert hasattr(m, 'get_move'), 'no get_move'",
        "assert 'tkinter' not in sys.modules, 'imported tkinter'",
        "assert threading.active_count() == 1, 'extra thread'",
        "print('%.2f' % (time.time() - t))",
    ])
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    check(results, "导入不弹窗 / 无副作用", p.returncode == 0,
          (p.stdout or "").strip() + (p.stderr or "").strip()[-160:])

    ai = load(SUB)
    check(results, "顶层定义 get_move(board, player)", hasattr(ai, "get_move"))

    # 3 空棋盘
    b = [["." for _ in range(N)] for _ in range(N)]
    mv = ai.get_move(b, "X")
    check(results, "空棋盘落在空位", L.legal(b, mv), "%r" % (mv,))

    # 4 执黑执白都能跑
    ok_both = True
    for st in ("X", "O"):
        b2 = L.from_stones([(7, 7, "X" if st == "O" else "O")])
        try:
            m = ai.get_move(b2, st)
            ok_both = ok_both and L.legal(b2, m)
        except Exception as e:
            ok_both = False
            print("   ", st, "异常", e)
    check(results, "执黑和执白都能正常运行", ok_both)

    # 5 能发现一步获胜
    win_board = L.from_stones([(7, 4, "X"), (7, 5, "X"), (7, 6, "X"), (7, 7, "X"),
                               (6, 6, "O"), (8, 8, "O"), (5, 5, "O"), (9, 3, "O")])
    mv = ai.get_move(win_board, "X")
    check(results, "能发现一步获胜", tuple(mv) in {(7, 3), (7, 8)}, "%r" % (tuple(mv),))

    # 6 能挡住一步威胁
    blk_board = L.from_stones([(7, 4, "O"), (7, 5, "O"), (7, 6, "O"), (7, 7, "O"),
                               (6, 6, "X"), (8, 8, "X"), (5, 5, "X"), (9, 3, "X")])
    mv = ai.get_move(blk_board, "X")
    check(results, "能挡住对手的成五点", tuple(mv) in {(7, 3), (7, 8)}, "%r" % (tuple(mv),))

    # 7 不修改 board + 返回合法 + 计时（随机局面抽样）
    import random
    random.seed(2026)
    bad_mutate = 0
    bad_legal = 0
    worst = 0.0
    total = 0.0
    steps = 0
    for _ in range(30):
        bb = L.new_board()
        turn = "X"
        for _ in range(random.randint(0, 40)):
            empty = [(r, c) for r in range(N) for c in range(N) if bb[r][c] == "."]
            if not empty:
                break
            r, c = random.choice(empty)
            bb[r][c] = turn
            if L.is_win_at(bb, r, c):
                break
            turn = "O" if turn == "X" else "X"
        snap = [row[:] for row in bb]
        t0 = time.perf_counter()
        m = ai.get_move(bb, turn)
        dt = time.perf_counter() - t0
        worst = max(worst, dt)
        total += dt
        steps += 1
        if bb != snap:
            bad_mutate += 1
        if not L.legal(bb, m) or not all(isinstance(x, int) for x in m):
            bad_legal += 1
    check(results, "不修改输入棋盘", bad_mutate == 0, "%d/30 次被改" % bad_mutate)
    check(results, "返回值是合法空位", bad_legal == 0, "%d/30 次非法" % bad_legal)
    check(results, "单步 3 秒内", worst < 3.0, "最慢 %.3fs" % worst)

    # 8 整局累计 —— 跑一整局看单方累计时间
    r = L.play_game(ai.get_move, ai.get_move, step_limit=3.0)
    per_side = {}
    for i, dt in enumerate(r["times"]):
        stone = "X" if i % 2 == 0 else "O"
        per_side[stone] = per_side.get(stone, 0.0) + dt
    check(results, "每方每局累计 60 秒内",
          max(per_side.values() or [0]) < 60.0,
          "黑 %.2fs / 白 %.2fs，%d 手" % (per_side.get("X", 0),
                                          per_side.get("O", 0), len(r["moves"])))
    check(results, "整局无异常/无超时", r["error"] is None, str(r["error"]))

    print("-" * 72)
    okn = sum(1 for _, ok, _ in results if ok)
    print("结果：%d/%d 项通过" % (okn, len(results)))
    if okn != len(results):
        print("有失败项，需修正。")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
