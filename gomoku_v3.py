# -*- coding: utf-8 -*-
"""
五子棋 AI —— v3 搜索版（最终版）

在 v2 的基础上只加一件事：**下完这一手之后，对手还能拿到什么**。
也就是从"1 层贪心"变成"2 层前瞻"。

v2 的结构性弱点（v1 也有，只是程度更重）：
  评估一个点时只看这个点对**现在**的棋盘值多少，不管下完之后局势变成什么样。
  于是有两种典型错误：
    - 自己下了一手漂亮的活三，但完全没压住对手的活三，
      对手下一手做成活四，我再堵已经晚了（先手被对手拿走）。
    - 对手某个点其实已经没威胁了，还是花一手去防，白白丢掉进攻节奏。

v3 的三层结构：
  1. 硬规则层（先判对错，再谈好坏）
     - 我能一步成五 -> 直接下。
     - 对手能一步成五 -> 必须堵。
     - 我能做出活四 / 双冲四 / 四三 / 双活三 -> 两步内不可阻挡，直接下。
  2. 冲四连击（VCF）：我能不能靠连续的强制手把对手逼死。
  3. 搜索层：negamax + 两层前瞻。把 v2 静态分最高的若干个候选逐个试下，
     然后在每个分支上让对手走他最舒服的一手，再回头用"谁握着先手"评估。
     关键细节（第一版这里写错了）：对手有冲四时，如果轮到我，我一堵就化解了，
     不能直接判输；只有"轮到他，而他的成五点有两个以上"才是真的挡不住。
     所以强制手要在节点开头单独处理，不能混进静态评分里。

耗时：候选只在已有棋子两格内，10 x 8 = 80 个叶节点，单步远低于 3 秒上限。

接口：顶层 get_move(board, player) -> (row, col)
"""

from gomoku_v2 import (T_FIVE, T_OPEN4, T_COMBO, T_DOUBLE3, T_FOUR, T_OPEN3,
                       V2_CENTER_W, v2_candidates, v2_point_score,
                       v2_shapes, v2_defend_weight)

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


# AI 引擎统一入口
def get_move(board, player):
    return v3_get_move(board, player)


if __name__ == "__main__":
    import time
    b = [["." for _ in range(15)] for _ in range(15)]
    print("空棋盘首选：", v3_get_move(b, "X"))
    b[7][7] = "X"
    b[7][8] = "O"
    b[8][8] = "X"
    b[8][10] = "O"
    t = time.perf_counter()
    mv = v3_get_move(b, "O")
    print("第 3 手：", mv, " 用时 %.3f 秒" % (time.perf_counter() - t))
