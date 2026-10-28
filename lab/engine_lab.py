# -*- coding: utf-8 -*-
"""
对照实验台：给任意两个 AI 摆盘对下，检查合法性、计时、记录棋谱。
不产生副作用，只读棋盘，所有写操作在副本上进行。
"""
import time

N = 15
EMPTY, BLACK, WHITE = ".", "X", "O"
DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))


def new_board():
    return [[EMPTY] * N for _ in range(N)]


def from_stones(stones):
    """stones: [(r, c, 'X'/'O'), ...]"""
    b = new_board()
    for r, c, s in stones:
        b[r][c] = s
    return b


def clone(board):
    return [row[:] for row in board]


def count_line(board, r, c):
    """以 (r,c) 为中心，四个方向最长的同色连子数。"""
    me = board[r][c]
    best = 1
    for dr, dc in DIRS:
        cnt = 1
        rr, cc = r + dr, c + dc
        while 0 <= rr < N and 0 <= cc < N and board[rr][cc] == me:
            cnt += 1
            rr += dr
            cc += dc
        rr, cc = r - dr, c - dc
        while 0 <= rr < N and 0 <= cc < N and board[rr][cc] == me:
            cnt += 1
            rr -= dr
            cc -= dc
        best = max(best, cnt)
    return best


def is_win_at(board, r, c):
    return board[r][c] != EMPTY and count_line(board, r, c) >= 5


def win_cells(board, r, c):
    """返回构成五连的那条线上的所有格子（用于截图标注）。"""
    me = board[r][c]
    for dr, dc in DIRS:
        line = [(r, c)]
        rr, cc = r + dr, c + dc
        while 0 <= rr < N and 0 <= cc < N and board[rr][cc] == me:
            line.append((rr, cc))
            rr += dr
            cc += dc
        rr, cc = r - dr, c - dc
        while 0 <= rr < N and 0 <= cc < N and board[rr][cc] == me:
            line.append((rr, cc))
            rr -= dr
            cc -= dc
        if len(line) >= 5:
            return sorted(line)
    return []


def is_full(board):
    for row in board:
        if EMPTY in row:
            return False
    return True


def legal(board, mv):
    if not (isinstance(mv, (tuple, list)) and len(mv) == 2):
        return False
    try:
        r, c = int(mv[0]), int(mv[1])
    except Exception:
        return False
    return 0 <= r < N and 0 <= c < N and board[r][c] == EMPTY


def play_game(engine_black, engine_white, opening=(), move_cap=225,
              step_limit=3.0, record=True):
    """
    返回 dict：winner('X'/'O'/'draw'), moves, times, error, board
    opening: 预置棋形 [(r,c,'X'),...]，之后由 AI 继续。
    """
    board = from_stones(opening) if opening else new_board()
    stone_of_black = BLACK

    moves = []
    times = []
    err = None
    turn = BLACK

    # 预置棋子里若已分出胜负，直接结束
    for r, c, s in opening:
        if is_win_at(board, r, c):
            return dict(winner=s, moves=[], times=[], error="opening_win",
                        board=board)

    while len(moves) + len(opening) < move_cap:
        if is_full(board):
            return dict(winner="draw", moves=moves, times=times, error=None,
                        board=board)

        snap = [row[:] for row in board]
        eng = engine_black if turn == BLACK else engine_white
        t0 = time.perf_counter()
        try:
            mv = eng(board, turn)
        except Exception as e:                        # AI 自己崩了
            return dict(winner=("O" if turn == BLACK else "X"), moves=moves,
                        times=times, error="exception: %r" % (e,), board=board)
        dt = time.perf_counter() - t0

        if board != snap:
            return dict(winner=("O" if turn == BLACK else "X"), moves=moves,
                        times=times, error="mutated_board", board=snap)
        if dt > step_limit:
            return dict(winner=("O" if turn == BLACK else "X"), moves=moves,
                        times=times, error="timeout %.2fs" % dt, board=board)
        if not legal(board, mv):
            return dict(winner=("O" if turn == BLACK else "X"), moves=moves,
                        times=times, error="illegal %r" % (mv,), board=board)

        r, c = int(mv[0]), int(mv[1])
        board[r][c] = turn
        times.append(dt)
        moves.append((r, c, turn))

        if is_win_at(board, r, c):
            return dict(winner=turn, moves=moves, times=times, error=err,
                        board=board)
        turn = WHITE if turn == BLACK else BLACK

    return dict(winner="draw", moves=moves, times=times, error=err, board=board)


def fmt_move(mv):
    """把 (r,c) 变成人类习惯的坐标：列用字母 A~O，行用 1~15（从下往上数）。"""
    r, c = mv
    return "%s%d" % (chr(ord("A") + c), N - r)


def render(board, mark=None):
    """终端里打印棋盘，便于人工看局。"""
    out = ["    " + " ".join("%2d" % c for c in range(N))]
    for r in range(N):
        row = "%2d  " % (N - r)
        cells = []
        for c in range(N):
            if mark and (r, c) == mark:
                cells.append("<" + ("#" if board[r][c] == BLACK else "o") + ">")
            else:
                cells.append(" " + ("#" if board[r][c] == BLACK
                                    else ("o" if board[r][c] == WHITE else ".") ) + " ")
        out.append(row + "".join(cells))
    return "\n".join(out)
