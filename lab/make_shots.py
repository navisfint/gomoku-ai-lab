# -*- coding: utf-8 -*-
"""
生成关键棋局截图（不依赖屏幕，直接按 GUI 的样式把棋盘画出来并标注）。

输出到 screenshots/ 目录：
  01_关键棋局_v1漏防.png      —— v1 下错的那一手 vs 正解
  02_同局面_v2_v3正确防守.png  —— 同一局面下 v2 / v3 的选择
  03_v1落败终局.png            —— 那一局最后被五连的棋面
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import engine_lab as L
import gomoku_v1 as v1
import gomoku_v2 as v2
import gomoku_v3 as v3
import run_lab as R

OUT = os.path.join(ROOT, "截图")
N = 15
CELL = 42
MARGIN = 40
STONE_R = 17

C_BG = (246, 243, 238)
C_BOARD = (231, 200, 142)
C_GRID = (138, 106, 59)
C_TEXT = (46, 42, 36)
C_SUB = (122, 113, 102)
C_BAD = (192, 57, 43)
C_GOOD = (35, 122, 74)

F_TITLE = "C:/Windows/Fonts/msyhbd.ttc"
F_BODY = "C:/Windows/Fonts/msyh.ttc"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def px(i):
    return MARGIN + i * CELL


def draw_board(draw, stones, marks=None, threat=None):
    marks = marks or []
    w = MARGIN * 2 + CELL * (N - 1)
    draw.rectangle([0, 0, w, w], fill=C_BOARD)
    for i in range(N):
        wd = 2 if i in (0, N - 1) else 1
        draw.line([px(0), px(i), px(N - 1), px(i)], fill=C_GRID, width=wd)
        draw.line([px(i), px(0), px(i), px(N - 1)], fill=C_GRID, width=wd)
    for r in (3, 7, 11):
        for c in (3, 7, 11):
            x, y = px(c), px(r)
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=C_GRID)

    fb = font(F_BODY, 13)
    for i in range(N):
        draw.text((px(i) - 4, px(N - 1) + 8), chr(ord("A") + i), font=fb, fill=C_GRID)
        lab = str(N - i)
        draw.text((MARGIN - 26, px(i) - 8), lab, font=fb, fill=C_GRID)

    # 威胁线（虚线）
    if threat:
        (r0, c0), (r1, c1) = threat
        x0, y0 = px(c0), px(r0)
        x1, y1 = px(c1), px(r1)
        n = 14
        for k in range(n):
            if k % 2:
                continue
            t0, t1 = k / float(n), (k + 1) / float(n)
            draw.line([x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0,
                       x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1],
                      fill=C_BAD, width=3)

    for r, c, s in stones:
        x, y = px(c), px(r)
        if s == "X":
            draw.ellipse([x - STONE_R, y - STONE_R, x + STONE_R, y + STONE_R],
                         fill=(43, 43, 43), outline=(17, 17, 17))
            draw.ellipse([x - STONE_R + 5, y - STONE_R + 5,
                          x - STONE_R + 12, y - STONE_R + 12], fill=(90, 90, 90))
        else:
            draw.ellipse([x - STONE_R, y - STONE_R, x + STONE_R, y + STONE_R],
                         fill=(255, 255, 255), outline=(185, 174, 156))
            draw.ellipse([x - STONE_R + 5, y - STONE_R + 5,
                          x - STONE_R + 12, y - STONE_R + 12], fill=(242, 238, 231))

    for mv, kind, _label in marks:
        r, c = mv
        x, y = px(c), px(r)
        col = C_BAD if kind == "bad" else C_GOOD
        R = STONE_R + 8
        if kind == "bad":
            draw.line([x - R, y - R, x + R, y + R], fill=col, width=5)
            draw.line([x - R, y + R, x + R, y - R], fill=col, width=5)
        else:
            draw.ellipse([x - R, y - R, x + R, y + R], outline=col, width=5)


def paste_board(img, stones, marks=None, threat=None, top=0):
    board = Image.new("RGB", (MARGIN * 2 + CELL * (N - 1),) * 2, C_BOARD)
    draw_board(ImageDraw.Draw(board), stones, marks, threat)
    img.paste(board, (24, top))


def wrap(draw, text, f, width, x, y, fill, gap=8):
    line = ""
    for ch in text:
        if draw.textlength(line + ch, font=f) > width:
            draw.text((x, y), line, font=f, fill=fill)
            y += f.size + gap
            line = ch
        else:
            line += ch
    if line:
        draw.text((x, y), line, font=f, fill=fill)
        y += f.size + gap
    return y


def shot(name, title, subtitle, stones, marks=None, threat=None, notes=None,
         footer="", legend=None):
    legend = legend or []
    W = MARGIN * 2 + CELL * (N - 1) + 48
    H = (78 + (MARGIN * 2 + CELL * (N - 1)) + 22 * len(legend) + 30
         + (26 * len(notes or [])) + 34)
    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)
    d.text((24, 18), title, font=font(F_TITLE, 20), fill=C_TEXT)
    d.text((24, 48), subtitle, font=font(F_BODY, 13), fill=C_SUB)
    paste_board(img, stones, marks, threat, top=78)
    y = 78 + MARGIN * 2 + CELL * (N - 1) + 12
    for text, kind in legend:
        col = C_BAD if kind == "bad" else (C_GOOD if kind == "good" else C_TEXT)
        d.text((24, y), text, font=font(F_BODY, 14), fill=col)
        y += 22
    y += 10
    for line, kind in (notes or []):
        col = C_BAD if kind == "bad" else (C_GOOD if kind == "good" else C_TEXT)
        d.text((24, y), line, font=font(F_BODY, 14), fill=col)
        y += 26
    if footer:
        d.text((24, y + 6), footer, font=font(F_BODY, 11), fill=C_SUB)
    path = os.path.join(OUT, name)
    img.save(path)
    print("写出", path)
    return path


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)

    kstones, kturn = R.replay_key_game()
    kb = L.from_stones(kstones)
    mv1 = v1.v1_get_move(kb, kturn)
    mv2 = v2.v2_get_move(kb, kturn)
    mv3 = v3.v3_get_move(kb, kturn)

    s1 = v1.v1_score_cell(kb, mv1[0], mv1[1], kturn, "X")
    f7 = (8, 5)
    s2 = v1.v1_score_cell(kb, f7[0], f7[1], kturn, "X")

    # 图 1：v1 的错误落子 vs 正解
    shot("01_关键棋局_v1漏防.png",
         "关键棋局：AI（v1 原始版）执白第 28 手",
         "黑方在 F 列的 X X . X 中间一补就是活四，白方必须在这一手化解",
         kstones,
         marks=[(mv1, "bad", "v1 下的：%s" % L.fmt_move(mv1)),
                (f7, "good", "正解：%s" % L.fmt_move(f7))],
         threat=((6, 5), (9, 5)),
         legend=[("×  红叉：v1 实际下的 G6（自己做了一个冲四）", "bad"),
                 ("○  绿圈：正解 F7（占住黑方的活四成点）", "good"),
                 ("┄  红虚线：黑方在 F 列的一串子，中间补上即成活四", "bad")],
         notes=[("v1 的算分：下 G6 = %.0f 分，堵 F7 = %.0f 分 —— 它选了分数高的那个。"
                 % (s1, s2), "bad"),
                ("在 v1 眼里这两手都是「4 连」，活四和冲四分不出来，", "text"),
                ("于是它去做自己的冲四，把对手的活四放了过去。", "text")],
         footer="黑方下一手 F7 即成活四（两个成五点都空），白方挡不住，3 手内落败。")

    # 图 2：同一局面，v2 / v3 的选择
    shot("02_同局面_v2_v3正确防守.png",
         "同一局面：v2 优化版 / v3 试验版 都会化解这个威胁",
         "v2 直接占 F7，v3 先封 F10 一端，两条路都能让黑方失去活四",
         kstones,
         marks=[(mv2, "good", "v2：%s" % L.fmt_move(mv2)),
                (mv3, "good", "v3：%s" % L.fmt_move(mv3))],
         threat=((6, 5), (9, 5)),
         legend=[("○  绿圈：v2 下 F7 —— 直接把活四成点占掉", "good"),
                 ("○  绿圈：v3 下 F10 —— 先封这一列的一端", "good")],
         notes=[("v2 用九格窗口，F7 被识别成「活四成点」，权重压过一切进攻分。", "good"),
                ("v3 的两层前瞻算完发现：封 F10 之后黑方最强的点只剩可堵的冲四，", "good"),
                ("比直接占 F7 更划算，所以它选了另一条同样能解的路。", "good")],
         footer="正解不唯一：占住 F7，或先封掉 F5 / F10 任一端，都能让黑方做不成活四。")

    # 图 3：那一局的终局
    board = L.from_stones(kstones)
    turn = kturn
    while True:
        eng = v2.v2_get_move if turn == "X" else v1.v1_get_move
        mv = eng(board, turn)
        board[mv[0]][mv[1]] = turn
        if L.is_win_at(board, mv[0], mv[1]):
            win = L.win_cells(board, mv[0], mv[1])
            break
        turn = "O" if turn == "X" else "X"
    stones = [(r, c, board[r][c]) for r in range(N) for c in range(N)
              if board[r][c] != "."]
    shot("03_v1落败终局.png",
         "同一局终局：白方（v1）被黑方五连",
         "从那一手算起，黑方只用了 3 手就完成五连",
         stones,
         marks=[(win[0], "bad", ""), (win[-1], "bad", "")],
         legend=[("×  红叉：黑方五连的两端", "bad")],
         notes=[("整个对局不到 1 秒（v1 每步约 0.005 秒），", "text"),
                ("输棋不是因为算得慢，而是因为评价棋形的规则不对。", "text")],
         footer="这一局：黑方由 v2 代打（模拟正常棋手的走法），白方为 v1，共 31 手。")


if __name__ == "__main__":
    main()
