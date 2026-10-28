# -*- coding: utf-8 -*-
"""
五子棋 AI —— v1 原始版（修改前）

这是最初的落子策略版本，也是本实验的对照基准。
算法：对每个空位算一个分数，分数 = 自己的连续子价值 + 0.85 x 对手的连续子价值，
取分数最高的空位落子（1 层贪心，不做任何搜索）。

v1 的已知局限（本实验要解决的问题就从这里来）：
  1. 只用"落点两侧连续同色棋子的个数"当棋形，看不见断点。
     像 X.X X（中间隔一个空）这种"跳四/跳三"，空隙两侧的棋子不算连续，
     所以在空隙点上的评分只有"1 颗子"，防守价值被严重低估 —— 该堵的没堵。
  2. 只取四个方向的最大值（max），不求和，双三、双四这类"两条线同时成威胁"
     的棋完全看不出来。
  3. 不区分活棋和死棋：一端被堵死的三连和活三同分，容易跑去堵一个
     其实已经威胁不到自己的死三，浪费一手。
  4. 没有"我一步五连"和"对手一步五连"的硬判断，全靠分数硬碰，
     当自己有个看起来更大的局部形状时，会去进攻而不去堵对手的直接胜点。

接口与接口要求一致：顶层 get_move(board, player) -> (row, col)
board 为 15x15 二维列表，"." 空位，"X" 黑棋，"O" 白棋。
"""

# ---------------------------------------------------------------- 常量
V1_VALUE = {0: 0, 1: 1, 2: 10, 3: 100, 4: 1000, 5: 100000}
V1_DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))
V1_DEFEND_W = 0.85      # 防守权重
V1_CENTER_W = 0.01      # 轻微的中心偏好，避免开局乱下


# ---------------------------------------------------------------- 工具
def v1_run(board, r, c, dr, dc, stone):
    """假设 (r, c) 已经是 stone，返回该方向上连续同色棋子的总数（含自身）。"""
    n = len(board)
    cnt = 1

    rr, cc = r + dr, c + dc
    while 0 <= rr < n and 0 <= cc < n and board[rr][cc] == stone:
        cnt += 1
        rr += dr
        cc += dc

    rr, cc = r - dr, c - dc
    while 0 <= rr < n and 0 <= cc < n and board[rr][cc] == stone:
        cnt += 1
        rr -= dr
        cc -= dc

    return cnt


def v1_score_cell(board, r, c, me, opp):
    """单点评分：自己的最大连子价值 + 加权后的对手最大连子价值。"""
    atk = 0
    dfd = 0
    for dr, dc in V1_DIRS:
        atk = max(atk, V1_VALUE[min(v1_run(board, r, c, dr, dc, me), 5)])
        dfd = max(dfd, V1_VALUE[min(v1_run(board, r, c, dr, dc, opp), 5)])
    return atk + V1_DEFEND_W * dfd


# ---------------------------------------------------------------- 对外接口
def v1_get_move(board, player):
    """v1 落子：全盘空位逐个打分，取最高分。"""
    n = len(board)
    opp = "O" if player == "X" else "X"
    mid = n // 2

    best = None
    best_score = -1.0
    for r in range(n):
        for c in range(n):
            if board[r][c] != ".":
                continue
            s = v1_score_cell(board, r, c, player, opp)
            s -= V1_CENTER_W * (abs(r - mid) + abs(c - mid))
            if s > best_score:
                best_score = s
                best = (r, c)

    if best is None:                      # 棋盘满了（正常不会走到）
        return (0, 0)
    return best


# AI 引擎统一入口
def get_move(board, player):
    return v1_get_move(board, player)


if __name__ == "__main__":
    b = [["." for _ in range(15)] for _ in range(15)]
    print("空棋盘首选：", v1_get_move(b, "X"))
    b[7][7] = "X"
    print("黑已在中心，白应下：", v1_get_move(b, "O"))
