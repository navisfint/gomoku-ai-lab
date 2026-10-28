# -*- coding: utf-8 -*-
# ============================================================================
#  以下为 GUI 人机对弈界面（与上面的 AI 引擎合并为同一个文件）
#  运行：双击本文件，或 python gomoku_gui.py
# ============================================================================
import os
import time
import datetime

import tkinter as tk
from tkinter import messagebox, filedialog

BOARD_N = 15
CELL = 44
MARGIN = 34
STONE_R = 18

C_BG = "#F6F3EE"
C_BOARD = "#E7C88E"
C_BOARD_DARK = "#D9B573"
C_GRID = "#8A6A3B"
C_TEXT = "#2E2A24"
C_SUB = "#7A7166"
C_ACCENT = "#B4482E"
C_OK = "#2E7D4F"
C_PANEL = "#FFFFFF"
C_LINE = "#E3DCCF"

VER_INFO = {
    "v1 原始版": ("v1_get_move", "连续子计数 + 单层贪心（修改前）"),
    "v2 优化版": ("v2_get_move", "九格窗口棋形识别 + 必胜必堵（最终版）"),
    "v3 试验版": ("v3_get_move", "v2 + 冲四搜索 + 两层前瞻（实测未提升）"),
}


def engine_of(name):
    return {"v1_get_move": v1_get_move,
            "v2_get_move": v2_get_move,
            "v3_get_move": v3_get_move}[VER_INFO[name][0]]


def coord_name(r, c):
    """(row, col) -> 'H8' 这种人类习惯的坐标。"""
    return "%s%d" % (chr(ord("A") + c), BOARD_N - r)


class GomokuApp(object):
    def __init__(self, root):
        self.root = root
        self.root.title("五子棋 AI 人机对弈 · 15×15")
        self.root.configure(bg=C_BG)
        self.root.resizable(False, False)

        self.board = [["." for _ in range(BOARD_N)] for _ in range(BOARD_N)]
        self.history = []              # [(r, c, stone)]
        self.human_stone = "X"
        self.ai_stone = "O"
        self.ver = "v2 优化版"
        self.game_over = False
        self.busy = False
        self.last_move = None
        self.win_line = []
        self.ai_last = None            # (move, seconds, reason)
        self.record = []               # [(stone, move, seconds, reason)]

        self._after_ids = set()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.new_game()

    def _later(self, ms, fn):
        """登记一个定时回调，关窗口时可以统一取消，避免销毁后回调报错。"""
        aid = self.root.after(ms, fn)
        self._after_ids.add(aid)
        return aid

    def _cancel_all(self):
        for aid in list(self._after_ids):
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()

    def on_close(self):
        self._cancel_all()
        self.root.destroy()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # 标题
        head = tk.Frame(self.root, bg=C_BG)
        head.pack(fill="x", padx=24, pady=(16, 6))
        tk.Label(head, text="五子棋 AI 人机对弈", bg=C_BG, fg=C_TEXT,
                 font=("Microsoft YaHei UI", 17, "bold")).pack(side="left")
        tk.Label(head, text="  15 × 15  ·  观察 → 分析 → 改进 → 验证",
                 bg=C_BG, fg=C_SUB,
                 font=("Microsoft YaHei UI", 9)).pack(side="left", pady=(6, 0))

        body = tk.Frame(self.root, bg=C_BG)
        body.pack(padx=24, pady=(0, 6))

        self.canvas = tk.Canvas(body, width=MARGIN * 2 + CELL * (BOARD_N - 1),
                                height=MARGIN * 2 + CELL * (BOARD_N - 1),
                                bg=C_BOARD, highlightthickness=0, cursor="hand2")
        self.canvas.grid(row=0, column=0)
        self.canvas.bind("<Button-1>", self.on_click)

        panel = tk.Frame(body, bg=C_BG, width=340)
        panel.grid(row=0, column=1, sticky="n", padx=(20, 0))
        panel.grid_propagate(False)
        self._build_panel(panel)

        # 状态栏
        self.status = tk.Label(self.root, text="", bg=C_BOARD_DARK, fg="#4A3A20",
                               anchor="w", padx=14, pady=6,
                               font=("Microsoft YaHei UI", 9))
        self.status.pack(fill="x", side="bottom")

    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=C_LINE)
        outer.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(outer, bg=C_PANEL)
        inner.pack(fill="x", padx=1, pady=1)
        tk.Label(inner, text=title, bg=C_PANEL, fg=C_SUB,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=14, pady=(10, 4))
        box = tk.Frame(inner, bg=C_PANEL)
        box.pack(fill="x", padx=10, pady=(0, 12))
        return box

    def _build_panel(self, panel):
        # AI 版本
        box = self._card(panel, "AI 版本")
        self.ver_var = tk.StringVar(value=self.ver)
        for name in ("v1 原始版", "v2 优化版", "v3 试验版"):
            rb = tk.Radiobutton(box, text=name, variable=self.ver_var, value=name,
                                bg=C_PANEL, fg=C_TEXT, activebackground=C_PANEL,
                                selectcolor=C_PANEL, anchor="w",
                                font=("Microsoft YaHei UI", 10),
                                command=self.on_ver_change)
            rb.pack(anchor="w")
            tk.Label(box, text="    " + VER_INFO[name][1], bg=C_PANEL, fg=C_SUB,
                     font=("Microsoft YaHei UI", 8)).pack(anchor="w")

        # 执子
        box = self._card(panel, "我执")
        self.side_var = tk.StringVar(value="black")
        for val, txt in (("black", "黑棋（先手）"), ("white", "白棋（后手）")):
            tk.Radiobutton(box, text=txt, variable=self.side_var, value=val,
                           bg=C_PANEL, fg=C_TEXT, activebackground=C_PANEL,
                           selectcolor=C_PANEL, anchor="w",
                           font=("Microsoft YaHei UI", 10),
                           command=self.on_side_change).pack(anchor="w")

        # 操作
        box = self._card(panel, "操作")
        g = tk.Frame(box, bg=C_PANEL)
        g.pack(fill="x")
        for txt, cmd in (("新对局", self.new_game), ("悔棋", self.undo),
                         ("保存截图", self.save_shot), ("导出棋谱", self.export_record)):
            tk.Button(g, text=txt, command=cmd, relief="flat", bg="#F1EBE0",
                      fg=C_TEXT, activebackground="#E4DAC8",
                      font=("Microsoft YaHei UI", 9), padx=8, pady=5,
                      bd=0).pack(side="left", padx=(0, 6))

        # AI 本手
        box = self._card(panel, "AI 本手")
        self.ai_lbl = tk.Label(box, text="—", bg=C_PANEL, fg=C_TEXT, justify="left",
                               anchor="w", font=("Microsoft YaHei UI", 9))
        self.ai_lbl.pack(fill="x")

        # 记录
        box = self._card(panel, "落子记录")
        wrap = tk.Frame(box, bg=C_PANEL)
        wrap.pack(fill="both", expand=True)
        self.log = tk.Text(wrap, height=11, width=38, bg="#FCFAF6", fg=C_TEXT,
                           relief="flat", font=("Consolas", 9), padx=8, pady=6,
                           highlightthickness=1, highlightbackground=C_LINE)
        sb = tk.Scrollbar(wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log.tag_configure("me", foreground="#1F4E79")
        self.log.tag_configure("ai", foreground=C_ACCENT)
        self.log.tag_configure("sys", foreground=C_SUB)

    # --------------------------------------------------------------- 绘图
    def px(self, i):
        return MARGIN + i * CELL

    def draw(self):
        cv = self.canvas
        cv.delete("all")
        # 棋盘底
        cv.create_rectangle(0, 0, MARGIN * 2 + CELL * (BOARD_N - 1),
                            MARGIN * 2 + CELL * (BOARD_N - 1),
                            fill=C_BOARD, outline="")
        # 网格
        end = self.px(BOARD_N - 1)
        for i in range(BOARD_N):
            w = 2 if i in (0, BOARD_N - 1) else 1
            cv.create_line(self.px(0), self.px(i), end, self.px(i), fill=C_GRID, width=w)
            cv.create_line(self.px(i), self.px(0), self.px(i), end, fill=C_GRID, width=w)
        # 星位
        for r in (3, 7, 11):
            for c in (3, 7, 11):
                x, y = self.px(c), self.px(r)
                cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill=C_GRID, outline="")
        # 坐标
        for i in range(BOARD_N):
            cv.create_text(self.px(i), MARGIN * 2 + CELL * (BOARD_N - 1) + 14,
                           text=chr(ord("A") + i), fill=C_GRID,
                           font=("Consolas", 8))
            cv.create_text(MARGIN - 18, self.px(i), text=str(BOARD_N - i),
                           fill=C_GRID, font=("Consolas", 8))

        # 棋子
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                s = self.board[r][c]
                if s == ".":
                    continue
                x, y = self.px(c), self.px(r)
                if s == "X":
                    cv.create_oval(x - STONE_R, y - STONE_R, x + STONE_R, y + STONE_R,
                                   fill="#2B2B2B", outline="#111111")
                    cv.create_oval(x - STONE_R + 4, y - STONE_R + 4,
                                   x - STONE_R + 12, y - STONE_R + 12,
                                   fill="#5A5A5A", outline="")
                else:
                    cv.create_oval(x - STONE_R, y - STONE_R, x + STONE_R, y + STONE_R,
                                   fill="#FFFFFF", outline="#B9AE9C")
                    cv.create_oval(x - STONE_R + 4, y - STONE_R + 4,
                                   x - STONE_R + 12, y - STONE_R + 12,
                                   fill="#F4F1EA", outline="")

        # 最后一手
        if self.last_move and self.board[self.last_move[0]][self.last_move[1]] != ".":
            r, c = self.last_move
            x, y = self.px(c), self.px(r)
            col = "#FF6B4A" if self.board[r][c] == "X" else C_ACCENT
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=col, outline="")

        # 五连高亮
        if len(self.win_line) >= 5:
            p0 = self.px(self.win_line[0][1]), self.px(self.win_line[0][0])
            p1 = self.px(self.win_line[-1][1]), self.px(self.win_line[-1][0])
            cv.create_line(p0[0], p0[1], p1[0], p1[1], fill=C_ACCENT,
                           width=4, dash=(6, 4))

    # --------------------------------------------------------------- 逻辑
    def new_game(self):
        if self.busy:
            return
        self.board = [["." for _ in range(BOARD_N)] for _ in range(BOARD_N)]
        self.history = []
        self.record = []
        self.game_over = False
        self.last_move = None
        self.win_line = []
        self.ai_last = None
        self.log.delete("1.0", "end")
        self.ai_lbl.configure(text="—")
        self.human_stone = "X" if self.side_var.get() == "black" else "O"
        self.ai_stone = "O" if self.human_stone == "X" else "X"
        self.ver = self.ver_var.get()
        self._set_status("新对局开始：AI 使用 %s，你执%s。"
                         % (self.ver, "黑" if self.human_stone == "X" else "白"))
        self._sys("AI 版本：%s（%s）" % (self.ver, VER_INFO[self.ver][1]))
        self.draw()
        if self.human_stone == "O":
            self._later(120, self.ai_turn)

    def on_ver_change(self):
        self.ver = self.ver_var.get()
        self._sys("切换 AI 版本 -> %s（下一手生效）" % self.ver)
        self._set_status("AI 版本已切换为 %s" % self.ver)

    def on_side_change(self):
        if self.history:
            if not messagebox.askyesno("重新开始", "切换执子需要重开一局，继续？"):
                return
        self.new_game()

    def on_click(self, ev):
        if self.busy or self.game_over:
            return
        c = int(round((ev.x - MARGIN) / float(CELL)))
        r = int(round((ev.y - MARGIN) / float(CELL)))
        if not (0 <= r < BOARD_N and 0 <= c < BOARD_N):
            return
        if self.board[r][c] != ".":
            return
        self.place(r, c, self.human_stone, 0.0, "我")
        if self.game_over:
            return
        self._later(60, self.ai_turn)

    def place(self, r, c, stone, secs, who, reason=""):
        self.board[r][c] = stone
        self.history.append((r, c, stone))
        self.last_move = (r, c)
        self.record.append((stone, (r, c), secs, reason))
        line = self.win_line_at(r, c)
        if line:
            self.win_line = line
            self.game_over = True
        self.draw()

        tag = "me" if stone == self.human_stone else "ai"
        if who == "AI":
            self.log.insert("end", "%2d. %-3s AI %-4s %5.3fs %s\n"
                            % (len(self.history), stone, coord_name(r, c), secs, reason), tag)
        else:
            self.log.insert("end", "%2d. %-3s 我 %-4s\n"
                            % (len(self.history), stone, coord_name(r, c)), tag)
        self.log.see("end")

        if self.game_over:
            if stone == self.human_stone:
                self._set_status("你赢了。最后一手 %s。" % coord_name(r, c))
                self._sys("对局结束：你胜")
            else:
                self._set_status("AI 赢了。最后一手 %s。" % coord_name(r, c))
                self._sys("对局结束：AI 胜")
        elif len(self.history) >= BOARD_N * BOARD_N:
            self.game_over = True
            self._set_status("棋盘已满，平局。")
            self._sys("对局结束：平局")

    def win_line_at(self, r, c):
        me = self.board[r][c]
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            line = [(r, c)]
            rr, cc = r + dr, c + dc
            while 0 <= rr < BOARD_N and 0 <= cc < BOARD_N and self.board[rr][cc] == me:
                line.append((rr, cc))
                rr += dr
                cc += dc
            rr, cc = r - dr, c - dc
            while 0 <= rr < BOARD_N and 0 <= cc < BOARD_N and self.board[rr][cc] == me:
                line.insert(0, (rr, cc))
                rr -= dr
                cc -= dc
            if len(line) >= 5:
                return line
        return []

    def ai_turn(self):
        # 窗口可能已经被关闭，此时排队中的 after 回调会打到不存在的控件上
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        if self.game_over or self.busy:
            return
        self.busy = True
        self._set_status("AI 思考中…")
        self.root.update_idletasks()
        self._later(10, self._ai_compute)

    def _ai_compute(self):
        board_copy = [row[:] for row in self.board]
        eng = engine_of(self.ver)
        t0 = time.perf_counter()
        try:
            mv = eng(board_copy, self.ai_stone)
        except Exception as e:
            self.busy = False
            messagebox.showerror("AI 出错", repr(e))
            return
        dt = time.perf_counter() - t0

        if self.board != board_copy:
            self.busy = False
            messagebox.showerror("严重问题", "AI 修改了输入棋盘，已中止。")
            return
        if not (isinstance(mv, (tuple, list)) and len(mv) == 2):
            self.busy = False
            messagebox.showerror("AI 出错", "返回值不是两个整数：%r" % (mv,))
            return
        r, c = int(mv[0]), int(mv[1])
        if not (0 <= r < BOARD_N and 0 <= c < BOARD_N) or self.board[r][c] != ".":
            self.busy = False
            messagebox.showerror("AI 出错", "落子不合法：%r" % (mv,))
            return

        reason = self.explain(r, c)
        self.ai_lbl.configure(
            text="落子 %s\n用时 %.3f 秒\n判断 %s" % (coord_name(r, c), dt, reason))
        self.busy = False
        self.place(r, c, self.ai_stone, dt, "AI", reason)
        self._set_status("AI 落子 %s，用时 %.3f 秒，%s。轮到你。"
                         % (coord_name(r, c), dt, reason))

    def explain(self, r, c):
        """给这一手写一句人话解释，方便复盘时看 AI 在想什么。"""
        opp = "O" if self.ai_stone == "X" else "X"
        b = self.board
        if v2_point_score(b, r, c, self.ai_stone, opp) >= T_FIVE:
            return "成五点，直接赢"
        for rr in range(BOARD_N):
            for cc in range(BOARD_N):
                if b[rr][cc] == "." and v2_point_score(b, rr, cc, opp, self.ai_stone) >= T_FIVE:
                    return "堵对手的成五点"
        shapes = v2_shapes(b, r, c, self.ai_stone, opp)
        cnt = {}
        for s in shapes:
            cnt[s] = cnt.get(s, 0) + 1
        if cnt.get("open4"):
            return "做活四（两步必胜）"
        if cnt.get("four", 0) >= 2 or (cnt.get("four") and cnt.get("open3")):
            return "双四 / 四三，两步必胜"
        if cnt.get("open3", 0) >= 2:
            return "双活三，对手只能挡一边"
        if cnt.get("open3"):
            return "做活三"
        if cnt.get("four"):
            return "冲四，强制对手应一手"
        return "按局面评分选点"

    def undo(self):
        if self.busy:
            return
        if not self.history:
            return
        # 退回到自己该走的状态（通常退两手）
        n = 0
        while self.history and n < 2:
            r, c, s = self.history.pop()
            self.board[r][c] = "."
            n += 1
            if s == self.human_stone:
                break
        if self.record:
            self.record.pop()
        self.game_over = False
        self.win_line = []
        self.last_move = self.history[-1][:2] if self.history else None
        self.log.delete("1.0", "end")
        for i, (s, mv, secs, reason) in enumerate(self.record):
            who = "我" if s == self.human_stone else "AI"
            tag = "me" if s == self.human_stone else "ai"
            self.log.insert("end", "%2d. %-3s %s %-4s\n"
                            % (i + 1, s, who, coord_name(mv[0], mv[1])), tag)
        self.draw()
        self._set_status("已悔棋。" if self.history else "已回到开局。")
        if self.history and self.history[-1][2] != self.human_stone:
            self._later(60, self.ai_turn)

    # --------------------------------------------------------------- 输出
    def _sys(self, txt):
        self.log.insert("end", "· %s\n" % txt, "sys")
        self.log.see("end")

    def _set_status(self, txt):
        self.status.configure(text=txt)

    def save_shot(self):
        default = "对局_%s.png" % datetime.datetime.now().strftime("%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title="保存棋局截图", defaultextension=".png",
            initialfile=default, filetypes=[("PNG 图片", "*.png")])
        if not path:
            return
        if self.capture(path):
            self._set_status("截图已保存：%s" % path)
        else:
            messagebox.showwarning("保存失败", "截图需要 Pillow（pip install pillow）。")

    def capture(self, path):
        try:
            from PIL import ImageGrab
        except Exception:
            return False
        self.root.attributes("-topmost", True)
        self.root.update()
        time.sleep(0.25)
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        try:
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            img.save(path)
        except Exception:
            return False
        finally:
            self.root.attributes("-topmost", False)
        return True

    def export_record(self):
        path = filedialog.asksaveasfilename(
            title="导出棋谱", defaultextension=".txt",
            initialfile="棋谱_%s.txt" % datetime.datetime.now().strftime("%m%d_%H%M%S"),
            filetypes=[("文本文件", "*.txt")])
        if not path:
            return
        lines = ["# 五子棋对局记录",
                 "# AI 版本：%s（%s）" % (self.ver, VER_INFO[self.ver][1]),
                 "# 我执：%s" % ("黑" if self.human_stone == "X" else "白"),
                 "# 时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 ""]
        for i, (stone, mv, secs, reason) in enumerate(self.record):
            who = "我" if stone == self.human_stone else "AI"
            lines.append("%02d %s %s %s %.3fs %s"
                         % (i + 1, stone, who, coord_name(mv[0], mv[1]), secs, reason))
        lines.append("")
        lines.append("# 结果：%s" % ("你胜" if self.history and self.history[-1][2] == self.human_stone
                                 else ("AI 胜" if self.game_over else "未结束")))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self._set_status("棋谱已导出：%s" % path)

    # ------------------------------------------------------- 给脚本用的钩子
    def apply_position(self, stones, to_move, ver=None, human=None):
        """把棋盘摆成指定局面（用于复盘 / 生成截图）。

        to_move: 下一手轮到谁；human: 哪一方算"我"。两者分开传，
        因为复盘一个局面时，轮到走的一方不一定是人。
        """
        self.board = [["." for _ in range(BOARD_N)] for _ in range(BOARD_N)]
        for r, c, s in stones:
            self.board[r][c] = s
        self.history = [(r, c, s) for r, c, s in stones]
        self.record = [(s, (r, c), 0.0, "") for r, c, s in stones]
        if ver:
            self.ver = ver
            self.ver_var.set(ver)
        self.human_stone = human if human else to_move
        self.ai_stone = "O" if self.human_stone == "X" else "X"
        self.side_var.set("black" if self.human_stone == "X" else "white")
        self.game_over = False
        self.last_move = (stones[-1][0], stones[-1][1]) if stones else None
        self.win_line = []
        # 把棋谱写进记录面板，看起来就像刚下完的一局
        self.log.delete("1.0", "end")
        for i, (r, c, st) in enumerate(stones):
            who = "我" if st == self.human_stone else "AI"
            tag = "me" if st == to_move else "ai"
            self.log.insert("end", "%2d. %-3s %s %-4s\n"
                            % (i + 1, st, who, coord_name(r, c)), tag)
        self.log.see("end")
        self.ai_lbl.configure(text="轮到%s走\n版本：%s"
                             % ("我" if to_move == self.human_stone else " AI",
                                self.ver or ""))
        self.draw()
        self.root.update()
        return self


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.2)
    except Exception:
        pass
    GomokuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
