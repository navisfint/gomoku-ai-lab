# -*- coding: utf-8 -*-
"""GUI 冒烟测试：自动下一整局，验证主循环/胜负判定/悔棋/导出都不报错。"""
import importlib.util
import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import engine_lab as L
import gomoku_v2 as v2

GUI = os.path.join(ROOT, "gomoku_gui.py")


def load_gui():
    spec = importlib.util.spec_from_file_location("gui", GUI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_case(gui, ver, human):
    root = tk.Tk()
    app = gui.GomokuApp(root)
    app.ver_var.set(ver)
    app.side_var.set("black" if human == "X" else "white")
    app.new_game()
    root.update()

    plies = 0
    while not app.game_over and plies < 200:
        turn = "X" if len(app.history) % 2 == 0 else "O"
        if turn == app.human_stone:
            if app.busy:
                root.update()
                continue
            # 轮到"我"：用 v2 帮忙选一手，等价于人点了一下
            mv = v2.v2_get_move(app.board, app.human_stone)
            app.place(mv[0], mv[1], app.human_stone, 0.0, "我")
        else:
            app.ai_turn()
            for _ in range(200):
                root.update()
                time.sleep(0.005)      # 让 after(10) 的定时器有机会到期
                if not app.busy:
                    break
        plies += 1

    result = (app.game_over, len(app.history), app.win_line)
    # 悔棋
    app.undo()
    root.update()
    undone = len(app.history)
    # 导出棋谱
    path = os.path.join(HERE, "results", "_smoke_record.txt")
    app.export_record = app.export_record  # noqa
    lines = ["# smoke"]
    for st, mv, secs, reason in app.record:
        lines.append("%s %s" % (st, mv))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    app.on_close()
    return dict(ver=ver, human=human, finished=result[0], moves=result[1],
                win_line=len(result[2]), undo_left=undone)


def main():
    gui = load_gui()
    ok = True
    for ver in ("v1 原始版", "v2 优化版", "v3 试验版"):
        for human in ("X", "O"):
            r = run_case(gui, ver, human)
            print("%-10s 我执%s -> 结束=%s 共%d手 五连线%d格 悔棋后剩%d手"
                  % (r["ver"], "黑" if r["human"] == "X" else "白",
                     r["finished"], r["moves"], r["win_line"], r["undo_left"]))
            if r["moves"] < 4:
                ok = False
    print("冒烟测试：", "通过" if ok else "有问题")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
