# -*- coding: utf-8 -*-
"""
五子棋 AI 算法实验 —— 人机对弈演示程序

一个文件里同时带了三个版本，可以在界面上直接切换，方便做 v1 / v2 / v3 对照：
  v1 原始版：连续子计数 + 单层贪心（修改前）
  v2 优化版：九格窗口棋形识别 + 必胜必堵（改进后，也就是最终版）
  v3 试验版：v2 + 冲四搜索 + 两层前瞻（试过，实测没有变强，没有采用）

界面功能：切换 AI 版本、选执黑执白、悔棋、保存棋局截图、导出棋谱。

本文件面向人机对弈，界面逻辑与 AI 引擎完全分离；
AI 引擎是同目录下的 gomoku_v2.py（只有 get_move 函数）。
"""


# ==========================================================================
# 引擎 v1（原始版）
# ==========================================================================
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

# ==========================================================================
# 引擎 v2（优化版）
# ==========================================================================
# ---------------------------------------------------------------- 参数
V2_DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))

T_FIVE = 10000000      # 五连
T_OPEN4 = 1000000      # 活四：两个成五点，对手挡不住
T_COMBO = 800000       # 双冲四 / 四三：两步内不可阻挡
T_DOUBLE3 = 160000     # 双活三：对手只能堵一边，我另一边成活四
T_FOUR = 120000        # 单个冲四：只有一个成五点，对手一定会堵
T_OPEN3 = 12000        # 活三：下一手可成活四
T_SLEEP3 = 1200        # 眠三：只能成冲四
T_OPEN2 = 150          # 活二
T_SLEEP2 = 20          # 眠二

V2_DEFEND_W = 0.95     # 防守权重（对手强威胁）
V2_CENTER_W = 0.01     # 轻微中心偏好（开局去中间，别贴着边角）
V2_RADIUS = 2          # 只看已有棋子两格以内的空位


def v2_defend_weight(threat):
    """按威胁等级给防守权重。

    一刀切用一个权重会出问题：连对手的"活二"都当成头等大事去抢，
    结果双方互相拆点、谁也没法布局，棋局很容易拖成满盘和棋。
    真正的原则是——能立刻致命的必须堵，还早得很的可以放着，先抢自己的节奏。
    """
    if threat >= T_FOUR:
        return 1.00        # 冲四/活四级别的点，一步之差就是输
    if threat >= T_OPEN3:
        return 0.85        # 活三：不堵就成活四
    if threat >= T_SLEEP3:
        return 0.50        # 眠三：还差一手才成冲四
    return 0.35            # 活二及以下：不值得为它放弃自己的进攻


# 棋形模板。'1' 己方，'0' 空，'2' 对手或棋盘外。
# 顺序即优先级：先匹配更"强"的棋形。
V2_PATTERNS = (
    ("five", ("11111",)),
    ("open4", ("011110",)),
    ("four", ("11110", "01111", "11011", "10111", "11101")),
    ("open3", ("01110", "010110", "011010")),
    ("sleep3", ("11100", "00111", "11010", "01011",
                "10110", "01101", "11001", "10011")),
    ("open2", ("00110", "01100", "01010", "010010")),
    ("sleep2", ("11000", "00011", "10100", "00101",
                "10010", "01001", "10001")),
)

_SHAPE_CACHE = {}      # 9 格窗口串 -> 棋形名（真实对局里窗口高度重复，缓存很划算）


# ---------------------------------------------------------------- 棋形识别
def _v2_has(window, pat):
    """pat 是否出现在 window 中，且覆盖中心（索引 4）。

    必须要求覆盖中心：否则窗口边缘那颗远在天边的四连，会把当前落点的分抬起来，
    导致 AI 对着一个与自己无关的棋形出价。
    """
    L = len(pat)
    i = window.find(pat)
    while i >= 0:
        if i <= 4 < i + L:
            return True
        i = window.find(pat, i + 1)
    return False


def v2_shape_of(window):
    """把 9 格窗口归类成棋形名。"""
    got = _SHAPE_CACHE.get(window)
    if got is not None:
        return got
    got = "none"
    for name, pats in V2_PATTERNS:
        for p in pats:
            if _v2_has(window, p):
                got = name
                break
        if got != "none":
            break
    _SHAPE_CACHE[window] = got
    return got


def v2_window(board, r, c, dr, dc, me, opp):
    """以 (r,c) 为中心、沿 (dr,dc) 取 9 格窗口；中心视为已放上己方棋子。"""
    n = len(board)
    out = []
    for k in range(-4, 5):
        if k == 0:
            out.append("1")
            continue
        rr, cc = r + dr * k, c + dc * k
        if 0 <= rr < n and 0 <= cc < n:
            v = board[rr][cc]
            if v == me:
                out.append("1")
            elif v == opp:
                out.append("2")
            else:
                out.append("0")
        else:
            out.append("2")     # 棋盘外当成对手的棋子，天然把棋形判成死棋
    return "".join(out)


def v2_shapes(board, r, c, who, other):
    """返回 who 在 (r,c) 落子后，四个方向各自的棋形名。"""
    return [v2_shape_of(v2_window(board, r, c, dr, dc, who, other))
            for dr, dc in V2_DIRS]


def v2_point_score(board, r, c, who, other):
    """who 在 (r,c) 落子的价值。多方向同时成威胁时加分（v1 的 max 看不到这个）。"""
    shapes = v2_shapes(board, r, c, who, other)
    cnt = {}
    for s in shapes:
        cnt[s] = cnt.get(s, 0) + 1

    if cnt.get("five"):
        return T_FIVE
    if cnt.get("open4"):
        return T_OPEN4

    n_four = cnt.get("four", 0)
    n_open3 = cnt.get("open3", 0)
    # 威胁等级排序（这里的顺序就是 v2 相对 v1 最大的进步）：
    #   五 > 活四 > 双四/四三 > 双活三 > 单个冲四 > 活三
    # 注意"双活三"必须排在"单个冲四"前面：
    # 双活三是对手挡不住的必胜形，而单个冲四只是强制对手应一手，本身并不赢。
    if n_four >= 2:
        return T_COMBO
    if n_four == 1 and n_open3 >= 1:
        return T_COMBO
    if n_open3 >= 2:
        return T_DOUBLE3
    if n_four == 1:
        return T_FOUR
    if n_open3 == 1:
        return T_OPEN3
    if cnt.get("sleep3"):
        return T_SLEEP3
    return T_OPEN2 * cnt.get("open2", 0) + T_SLEEP2 * cnt.get("sleep2", 0)


# ---------------------------------------------------------------- 候选点
def v2_candidates(board, radius=None):
    """只考虑已有棋子邻近的空位；棋盘空则下天元。"""
    n = len(board)
    rad = V2_RADIUS if radius is None else radius
    stones = [(r, c) for r in range(n) for c in range(n) if board[r][c] != "."]
    if not stones:
        m = n // 2
        return [(m, m)]

    seen = set()
    out = []
    for sr, sc in stones:
        for dr in range(-rad, rad + 1):
            for dc in range(-rad, rad + 1):
                r, c = sr + dr, sc + dc
                if 0 <= r < n and 0 <= c < n and board[r][c] == "." and (r, c) not in seen:
                    seen.add((r, c))
                    out.append((r, c))
    return out


# ---------------------------------------------------------------- 对外接口
def v2_get_move(board, player):
    n = len(board)
    opp = "O" if player == "X" else "X"
    mid = n // 2

    cands = v2_candidates(board)
    if not cands:
        return (0, 0)

    # 规则 1：自己能一步成五 -> 立刻赢
    for p in cands:
        if v2_point_score(board, p[0], p[1], player, opp) >= T_FIVE:
            return p

    # 规则 2：对手能一步成五 -> 必须堵
    must_block = [p for p in cands
                  if v2_point_score(board, p[0], p[1], opp, player) >= T_FIVE]
    if must_block:
        return max(must_block,
                   key=lambda p: v2_point_score(board, p[0], p[1], player, opp))

    # 规则 3：自己的收益 + 按威胁等级加权的对手收益（抢下对手的好点，本身就是防守）
    best = cands[0]
    best_score = -1.0
    for p in cands:
        r, c = p
        their = v2_point_score(board, r, c, opp, player)
        s = v2_point_score(board, r, c, player, opp)
        s += v2_defend_weight(their) * their
        s -= V2_CENTER_W * (abs(r - mid) + abs(c - mid))
        if s > best_score:
            best_score = s
            best = p
    return best

# ==========================================================================
# 引擎 v3（搜索版 = 最终版）
# ==========================================================================
import time

V3_CAND_N = 10          # 根节点分支数
V3_INNER_N = 8          # 内层每个节点的分支数
V3_DEPTH = 2            # 前瞻层数：我一手 + 对手一手
V3_VCF_DEPTH = 8        # 冲四连击最多看几手
V3_VCF_NODES = 260      # 冲四搜索节点上限，兜住最坏情况
V3_WIN = 1000000000     # 搜索里用的"必赢"分值
V3_NODE_LIMIT = 30000   # 搜索节点上限
V3_TIME_LIMIT = 2.4     # 单步软时限（秒），平台给的是 3 秒

V3_DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))

# 搜索预算（每步重置）。宁可返回一个"够好"的着法，也绝不允许超时/卡死。
_BUDGET = {"nodes": 0, "t0": 0.0}


def _v3_reset_budget():
    _BUDGET["nodes"] = 0
    _BUDGET["t0"] = time.perf_counter()


def _v3_out_of_budget():
    _BUDGET["nodes"] += 1
    if _BUDGET["nodes"] > V3_NODE_LIMIT:
        return True
    if (_BUDGET["nodes"] & 255) == 0:
        if time.perf_counter() - _BUDGET["t0"] > V3_TIME_LIMIT:
            return True
    return False


def v3_is_forced_win(board, r, c, player, opp):
    """我在 (r,c) 落子后是否形成两步内不可阻挡的棋形。"""
    shapes = v2_shapes(board, r, c, player, opp)
    cnt = {}
    for s in shapes:
        cnt[s] = cnt.get(s, 0) + 1
    if cnt.get("five"):
        return True
    if cnt.get("open4"):                                       # 活四
        return True
    if cnt.get("four", 0) >= 2:                                # 双冲四
        return True
    if cnt.get("four", 0) >= 1 and cnt.get("open3", 0) >= 1:    # 四三
        return True
    if cnt.get("open3", 0) >= 2:                               # 双活三
        return True
    return False


def v3_opp_max_threat(board, opp, me):
    """对手在当前棋盘上单点能拿到的最高价值（>=T_FIVE 表示对手能一步成五）。"""
    best = 0
    for p in v2_candidates(board):
        s = v2_point_score(board, p[0], p[1], opp, me)
        if s > best:
            best = s
            if best >= T_FIVE:
                break
    return best


def v3_five_points(board, me, opp):
    """能让我一步成五的点。"""
    return [p for p in v2_candidates(board)
            if v2_point_score(board, p[0], p[1], me, opp) >= T_FIVE]


def v3_forcing_moves(board, me, opp):
    """能形成"冲四"级威胁的着法。

    返回 [(点, 'win'|'four'), ...]：
      'win'  —— 直接成五、活四或双四（对手挡不住）
      'four' —— 冲四，对手只有一个成五点，必须去堵
    """
    out = []
    for p in v2_candidates(board):
        shapes = v2_shapes(board, p[0], p[1], me, opp)
        cnt = {}
        for s in shapes:
            cnt[s] = cnt.get(s, 0) + 1
        if cnt.get("five") or cnt.get("open4") or cnt.get("four", 0) >= 2:
            out.append((p, "win"))
        elif cnt.get("four", 0) >= 1:
            out.append((p, "four"))
    return out


def v3_vcf(board, me, opp, depth=None, nodes=None):
    """连续冲四取胜搜索（VCF）。

    返回取胜的着法序列（第一手就是该下的），找不到返回 None。
    思路：冲四是"对手必须应"的强制手，所以可以只沿着这一条线往前推——
    对手没有选择，我也就不必展开他的其他应手，搜索量被压得很小。
    """
    if depth is None:
        depth = V3_VCF_DEPTH
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if depth <= 0 or nodes[0] > V3_VCF_NODES:
        return None
    if v3_five_points(board, me, opp):
        return []                       # 已经有成五点，等于赢

    for p, kind in v3_forcing_moves(board, me, opp):
        if kind == "win":
            return [p]
        wb = [row[:] for row in board]
        wb[p[0]][p[1]] = me
        blocks = v3_five_points(wb, me, opp)     # 我现在的成五点，对手必须堵
        if len(blocks) >= 2:
            return [p]                           # 双威胁，对手只能堵一个
        if not blocks:
            continue
        b = blocks[0]
        wb2 = [row[:] for row in wb]
        wb2[b[0]][b[1]] = opp
        # 关键：对手这一堵如果顺手给自己做成了成五点，我就得回头去堵，
        # 冲四链到此为止，这条线不算赢。（少了这一步检查，VCF 会算出一堆假胜）
        if v3_five_points(wb2, opp, me):
            continue
        sub = v3_vcf(wb2, me, opp, depth - 1, nodes)
        if sub is not None:
            return [p] + sub
    return None


def v3_best_point(board, me, opp):
    """board 上 me 单点能拿到的最高价值（>=T_FIVE 表示 me 能一步成五）。"""
    best = 0
    for p in v2_candidates(board):
        s = v2_point_score(board, p[0], p[1], me, opp)
        if s > best:
            best = s
            if best >= T_FIVE:
                break
    return best


def v3_opp_max_threat(board, opp, me):
    return v3_best_point(board, opp, me)


def v3_order(board, me, opp, k):
    """按静态价值排序，取前 k 个候选点（同时也返回完整排序结果）。"""
    mid = len(board) // 2
    scored = []
    for p in v2_candidates(board):
        r, c = p
        their = v2_point_score(board, r, c, opp, me)
        s = v2_point_score(board, r, c, me, opp)
        s += v2_defend_weight(their) * their
        s -= V2_CENTER_W * (abs(r - mid) + abs(c - mid))
        scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:k]], scored


def v3_scan(board, me, opp):
    """一次性把候选点算清楚：候选、我方每点价值、对手每点价值、双方最大值。

    对局中每个节点的开销主要就在这里，所以只扫一遍、全部复用，
    不要分别为了"找成五点""排序""静态评估"各扫一次。
    """
    cands = v2_candidates(board)
    sm = {}
    so = {}
    mm = 0
    mo = 0
    for p in cands:
        a = v2_point_score(board, p[0], p[1], me, opp)
        b = v2_point_score(board, p[0], p[1], opp, me)
        sm[p] = a
        so[p] = b
        if a > mm:
            mm = a
        if b > mo:
            mo = b
    return cands, sm, so, mm, mo


def v3_static(board, me, opp):
    """叶节点静态评估：这个局面上谁握着先手。

    用"我最好的单点"减"对手最好的单点"。轮到我时手里的威胁更值钱一点，
    所以对手那侧乘 0.9 —— 一个很粗但方向正确的先手度量。
    """
    return v3_best_point(board, me, opp) - 0.9 * v3_best_point(board, opp, me)


def v3_negamax(board, me, opp, depth):
    """轮 me 走时，me 视角的分值。

    节点开头先把强制手处理掉：
      - 我有成五点 -> 直接赢。
      - 对手有成五点 -> 我被迫堵；对手有两个以上成五点就是真的挡不住。
    这样处理之后，"对手有冲四"只在轮到他时才算致命，不会像我第一版那样
    在轮到我自己时也判成必输（那会让 AI 无谓地放弃好棋）。
    """
    cands, sm, so, mm, mo = v3_scan(board, me, opp)
    if not cands:
        return 0

    if mm >= T_FIVE:
        return V3_WIN
    if mo >= T_FIVE:
        theirs = [p for p in cands if so[p] >= T_FIVE]
        if len(theirs) >= 2:
            return -V3_WIN
        if _v3_out_of_budget():
            return mm - 0.9 * mo
        block = max(theirs, key=lambda p: sm[p])
        wb = [row[:] for row in board]
        wb[block[0]][block[1]] = me
        return -v3_negamax(wb, opp, me, depth)      # 强制手不消耗深度

    if depth <= 0 or _v3_out_of_budget():
        return mm - 0.9 * mo

    mid = len(board) // 2
    ranked = []
    for p in cands:
        s = sm[p] + v2_defend_weight(so[p]) * so[p]
        s -= V2_CENTER_W * (abs(p[0] - mid) + abs(p[1] - mid))
        ranked.append((s, p))
    ranked.sort(key=lambda x: -x[0])

    best = -2 * V3_WIN
    for _, p in ranked[:V3_INNER_N]:
        wb = [row[:] for row in board]
        wb[p[0]][p[1]] = me
        v = -v3_negamax(wb, opp, me, depth - 1)
        if v > best:
            best = v
    return best


def v3_choose(board, player, cand_n=None, use_vcf=True, use_depth2=True):
    _v3_reset_budget()
    opp = "O" if player == "X" else "X"
    K = V3_CAND_N if cand_n is None else cand_n

    cands = v2_candidates(board)
    if not cands:
        return (0, 0)

    # ---- 硬规则 1：我能一步成五
    for p in cands:
        if v2_point_score(board, p[0], p[1], player, opp) >= T_FIVE:
            return p

    # ---- 硬规则 2：对手能一步成五，必须堵
    must_block = [p for p in cands
                  if v2_point_score(board, p[0], p[1], opp, player) >= T_FIVE]
    if must_block:
        return max(must_block,
                   key=lambda p: v2_point_score(board, p[0], p[1], player, opp))

    # ---- 硬规则 3：能做出活四 / 双四 / 四三 / 双活三，直接收
    for p in cands:
        if v3_is_forced_win(board, p[0], p[1], player, opp):
            return p

    # ---- 冲四连击：靠连续的强制手把对手将死
    if use_vcf:
        seq = v3_vcf(board, player, opp)
        if seq:
            return seq[0]

    # ---- 排序取候选
    moves, _ = v3_order(board, player, opp, K)
    if len(moves) == 1:
        return moves[0]
    if not use_depth2:
        return moves[0]

    # ---- 搜索：我下这一手，然后让对手走他最舒服的一手
    best = moves[0]
    best_key = None
    for p in moves:
        wb = [row[:] for row in board]          # 只在副本上试下，绝不改输入棋盘
        wb[p[0]][p[1]] = player
        v = -v3_negamax(wb, opp, player, V3_DEPTH - 1)
        # 同分时偏向自己更实的点（避免在等价局面里挑到虚的位置）
        key = (v, v2_point_score(board, p[0], p[1], player, opp))
        if best_key is None or key > best_key:
            best_key = key
            best = p
    return best


def v3_get_move(board, player):
    return v3_choose(board, player)


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

