# -*- coding: utf-8 -*-
"""
五子棋 AI —— v2 优化版（修改后，单变量对照用）

相对 v1，只改一件事：**棋形的表示方式**。
  v1：从落点往两侧数"连续同色棋子个数" -> 看不见断点，也分不出活/死。
  v2：以落点为中心取 9 格窗口（4 左 + 自身 + 4 右），把窗口串成字符串，
      用棋形模板（含断点形状）判断这一条线到底是什么棋形：
      五连 / 活四 / 冲四 / 活三 / 眠三 / 活二 / 眠二 / 无。

为什么这能解决 v1 的问题：
  棋形本质上是由"一串格子"决定的，而不是由"连续个数"决定的。
  X X . X X 这种跳四，空隙那一点放进去就是五连；但在 v1 眼里，
  空隙左右各只有 1 颗相邻子，评分等于 1，于是被完全忽略。
  换成窗口匹配后，'11011' 这个模式直接命中"冲四"，该点立刻变成最高优先级的必堵点。

另外补了两条硬规则（也是"补上 v1 缺的操作"）：
  1. 自己能一步五连 -> 直接下（先赢，不等别的）。
  2. 对手能一步五连 -> 必须堵（这一步不堵就直接输，任何进攻都不划算）。

搜索深度与 v1 相同：仍是 1 层贪心（不向前推演），
所以 v1/v2 的差异只来自"评价方式"，方便做同条件对照。

接口：顶层 get_move(board, player) -> (row, col)
"""

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


# AI 引擎统一入口
def get_move(board, player):
    return v2_get_move(board, player)


if __name__ == "__main__":
    b = [["." for _ in range(15)] for _ in range(15)]
    print("空棋盘首选：", v2_get_move(b, "X"))
    # 跳四局面：白在 (7,5)(7,6)(7,8)(7,9)，黑必须堵 (7,7)
    for c in (5, 6, 8, 9):
        b[7][c] = "O"
    for c in (5, 6):
        b[9][c] = "X"
    print("跳四必堵点 (7,7)，v2 选：", v2_get_move(b, "X"))
