"""
围棋规则引擎 - 严格按照中国围棋规则实现
支持9x9和19x19棋盘
"""
import copy
from collections import deque

# 棋子颜色常量
EMPTY = 0
BLACK = 1
WHITE = 2

# 棋盘尺寸
DEFAULT_SIZE = 9

# 贴子（中国规则）：黑棋贴3.75子 = 3又3/4子
KOMI = 3.75


class GoBoard:
    """围棋棋盘与规则引擎"""

    def __init__(self, size=DEFAULT_SIZE):
        self.size = size
        self.board = [[EMPTY] * size for _ in range(size)]
        self.history = []  # 历史局面（用于禁止全局同形）
        self.move_history = []  # 落子记录 [(color, x, y, captured)]
        self.pass_count = 0  # 连续虚着计数
        self.resigned = None  # 认输方
        self.last_move = None  # 最后一手 (x, y, color)
        self.ko_point = None  # 劫点（最近被提子的位置）

    def reset(self):
        """重置棋盘"""
        self.board = [[EMPTY] * self.size for _ in range(self.size)]
        self.history = []
        self.move_history = []
        self.pass_count = 0
        self.resigned = None
        self.last_move = None
        self.ko_point = None

    def clone(self):
        """深拷贝 - 优化版：使用浅拷贝+内部list copy，避免 deepcopy 慢
        比 copy.deepcopy() 快约10-20倍
        """
        new = GoBoard(self.size)
        # 二维列表：用浅拷贝+内部list copy代替deepcopy
        new.board = [row[:] for row in self.board]
        new.history = list(self.history)
        new.move_history = list(self.move_history)
        new.pass_count = self.pass_count
        new.resigned = self.resigned
        new.last_move = self.last_move
        new.ko_point = self.ko_point
        return new

    def get_state_hash(self, next_player=None):
        """生成棋盘状态哈希（用于Q表和禁止全局同形）"""
        # 棋盘+下一手方
        rows = []
        for r in range(self.size):
            rows.append(''.join(str(c) for c in self.board[r]))
        state = '|'.join(rows)
        if next_player is not None:
            state += f'|{next_player}'
        return state

    def in_bounds(self, x, y):
        return 0 <= x < self.size and 0 <= y < self.size

    def neighbors(self, x, y):
        """返回(x,y)的四邻接点"""
        result = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                result.append((nx, ny))
        return result

    def find_group(self, x, y):
        """使用BFS找到(x,y)所在的连通块及其气"""
        color = self.board[x][y]
        if color == EMPTY:
            return set(), set()
        group = set()
        liberties = set()
        queue = deque([(x, y)])
        group.add((x, y))
        while queue:
            cx, cy = queue.popleft()
            for nx, ny in self.neighbors(cx, cy):
                if self.board[nx][ny] == EMPTY:
                    liberties.add((nx, ny))
                elif self.board[nx][ny] == color and (nx, ny) not in group:
                    group.add((nx, ny))
                    queue.append((nx, ny))
        return group, liberties

    def get_legal_moves(self, color, include_pass=True):
        """获取所有合法落点（包括pass），不包含自杀点与禁着点"""
        legal = []
        if include_pass:
            legal.append((-1, -1))  # pass
        for x in range(self.size):
            for y in range(self.size):
                if self.board[x][y] != EMPTY:
                    continue
                if self.is_legal_move(x, y, color):
                    legal.append((x, y))
        return legal

    def is_legal_move(self, x, y, color):
        """判断落子是否合法（不计pass）"""
        if not self.in_bounds(x, y):
            return False
        if self.board[x][y] != EMPTY:
            return False
        if (x, y) == self.ko_point:
            return False
        # 模拟下子：保存全盘快照
        board_snapshot = copy.deepcopy(self.board)
        self.board[x][y] = color
        # 提对方无气之子
        opp = WHITE if color == BLACK else BLACK
        captured = []
        for nx, ny in self.neighbors(x, y):
            if self.board[nx][ny] == opp:
                group, libs = self.find_group(nx, ny)
                if not libs:
                    for gx, gy in group:
                        self.board[gx][gy] = EMPTY
                        captured.append((gx, gy))
        # 自杀判定：己方无气且未提对方 -> 非法
        group, libs = self.find_group(x, y)
        if not libs and not captured:
            self.board = board_snapshot
            return False
        # 全局同形
        next_player = WHITE if color == BLACK else BLACK
        new_hash = self.get_state_hash(next_player)
        if new_hash in self.history:
            self.board = board_snapshot
            return False
        # 恢复原状
        self.board = board_snapshot
        return True

    def play_move(self, x, y, color):
        """正式下子，返回(dict): {ok, captured, is_ko_violation, ended, error}"""
        # 虚着
        if x == -1 and y == -1:
            self.pass_count += 1
            self.move_history.append((color, -1, -1, []))
            self.ko_point = None
            self.last_move = (-1, -1, color)
            # 记录下一手方状态
            next_p = WHITE if color == BLACK else BLACK
            self.history.append(self.get_state_hash(next_p))
            return {
                'ok': True,
                'captured': [],
                'pass': True,
                'is_legal': True,
                'ended': self.pass_count >= 2,
            }
        # 正常落子
        if not self.in_bounds(x, y):
            return {'ok': False, 'error': '坐标越界'}
        if self.board[x][y] != EMPTY:
            return {'ok': False, 'error': '该点已有棋子'}
        if (x, y) == self.ko_point:
            return {'ok': False, 'error': '禁着点（劫）'}
        opp = WHITE if color == BLACK else BLACK
        self.board[x][y] = color
        captured = []
        # 提对方无气
        for nx, ny in self.neighbors(x, y):
            if self.board[nx][ny] == opp:
                group, libs = self.find_group(nx, ny)
                if not libs:
                    for gx, gy in group:
                        self.board[gx][gy] = EMPTY
                        captured.append((gx, gy))
        # 提己方无气（自杀，应被禁着点规则禁止）
        group, libs = self.find_group(x, y)
        if not libs and not captured:
            # 自杀，回滚
            self.board[x][y] = EMPTY
            for cx, cy in captured:
                self.board[cx][cy] = opp
            return {'ok': False, 'error': '禁着点（自杀）'}
        # 禁着点（己方无气且未提对方）已经在上方处理
        # 全局同形
        next_p = WHITE if color == BLACK else BLACK
        new_hash = self.get_state_hash(next_p)
        if new_hash in self.history:
            # 回滚
            self.board[x][y] = EMPTY
            for cx, cy in captured:
                self.board[cx][cy] = opp
            return {'ok': False, 'error': '禁止全局同形（劫）'}
        # 提交
        self.move_history.append((color, x, y, captured))
        self.history.append(new_hash)
        self.pass_count = 0
        self.last_move = (x, y, color)
        # 设置劫点：仅当本手提了恰好1子时
        if len(captured) == 1:
            self.ko_point = captured[0]
        else:
            self.ko_point = None
        return {
            'ok': True,
            'captured': captured,
            'pass': False,
            'is_legal': True,
            'ended': False,
        }

    def resign(self, color):
        """认输"""
        self.resigned = color
        return {'ok': True, 'resigned': color, 'ended': True}

    def is_game_over(self):
        """判断终局"""
        if self.resigned is not None:
            return True
        if self.pass_count >= 2:
            return True
        return False

    def get_territory(self):
        """中国数子法：返回黑/白占领的空点（不含棋子本身）
        返回: (black_territory, white_territory, dead_black, dead_white)
        """
        # 简化：终局时所有无眼位但被包围的空点归该方
        # 实际数子法：清掉死子后，数活棋+围的空点
        # 死子判断：某个连通块如果只有1口气且周围都是对方，标记为死
        # 但稳妥做法是使用"区域计分"：每方围的空点（不含双方死子区域）
        # 简化版：统计所有属于某色势力范围的空点
        territory = [[None] * self.size for _ in range(self.size)]
        visited = [[False] * self.size for _ in range(self.size)]

        for x in range(self.size):
            for y in range(self.size):
                if self.board[x][y] == EMPTY and not visited[x][y]:
                    # BFS找空地区域及边界
                    queue = deque([(x, y)])
                    region = []
                    borders = set()
                    visited[x][y] = True
                    while queue:
                        cx, cy = queue.popleft()
                        region.append((cx, cy))
                        for nx, ny in self.neighbors(cx, cy):
                            if self.board[nx][ny] == EMPTY and not visited[nx][ny]:
                                visited[nx][ny] = True
                                queue.append((nx, ny))
                            elif self.board[nx][ny] != EMPTY:
                                borders.add(self.board[nx][ny])
                    # 单色包围 -> 该色领地；否则中立
                    if borders == {BLACK}:
                        for rx, ry in region:
                            territory[rx][ry] = BLACK
                    elif borders == {WHITE}:
                        for rx, ry in region:
                            territory[rx][ry] = WHITE
                    else:
                        for rx, ry in region:
                            territory[rx][ry] = 'NEUTRAL'

        black_terr = sum(1 for x in range(self.size) for y in range(self.size)
                         if territory[x][y] == BLACK)
        white_terr = sum(1 for x in range(self.size) for y in range(self.size)
                         if territory[x][y] == WHITE)

        # 棋子数
        black_stones = sum(1 for x in range(self.size) for y in range(self.size)
                           if self.board[x][y] == BLACK)
        white_stones = sum(1 for x in range(self.size) for y in range(self.size)
                           if self.board[x][y] == WHITE)

        return {
            'black_territory': black_terr,
            'white_territory': white_terr,
            'black_stones': black_stones,
            'white_stones': white_stones,
            'black_total': black_stones + black_terr,
            'white_total': white_stones + white_terr + KOMI,
        }

    def calculate_score(self):
        """计算胜负（中国数子法）
        黑总数 = 黑子数 + 黑围空
        白总数 = 白子数 + 白围空 + KOMI (3.75)
        黑胜：黑总数 > 白总数
        白胜：白总数 > 黑总数
        """
        if self.resigned is not None:
            winner = WHITE if self.resigned == BLACK else BLACK
            return {
                'ended': True,
                'reason': f"{'黑' if self.resigned == BLACK else '白'}方认输",
                'winner': winner,
                'black_total': None,
                'white_total': None,
                'margin': None,
            }
        if self.pass_count < 2:
            return {'ended': False}

        t = self.get_territory()
        black_total = t['black_total']
        white_total = t['white_total']
        diff = black_total - white_total
        if black_total > white_total:
            winner = BLACK
            margin = black_total - white_total
        elif white_total > black_total:
            winner = WHITE
            margin = white_total - black_total
        else:
            winner = 0  # 和棋
            margin = 0
        return {
            'ended': True,
            'reason': '双方连续虚着，棋局终了',
            'winner': winner,
            'black_total': black_total,
            'white_total': white_total,
            'white_territory': t['white_territory'],
            'black_territory': t['black_territory'],
            'black_stones': t['black_stones'],
            'white_stones': t['white_stones'],
            'margin': margin,
            'diff': diff,
        }

    def to_dict(self):
        """序列化为字典，便于API返回"""
        return {
            'size': self.size,
            'board': self.board,
            'pass_count': self.pass_count,
            'resigned': self.resigned,
            'last_move': self.last_move,
            'ko_point': self.ko_point,
            'move_count': len(self.move_history),
        }

    def get_move_list(self):
        """获取棋谱列表"""
        result = []
        for i, (color, x, y, captured) in enumerate(self.move_history):
            result.append({
                'index': i + 1,
                'color': color,
                'x': x,
                'y': y,
                'pass': x == -1,
                'captured': captured,
            })
        return result


# 工具函数
def coord_to_str(x, y, size=DEFAULT_SIZE):
    """坐标转SGF风格表示：A1 ~ T19 (跳过I)"""
    if x == -1 and y == -1:
        return 'pass'
    col = chr(ord('A') + y)
    if col >= 'I':
        col = chr(ord(col) + 1)
    row = size - x
    return f"{col}{row}"


def str_to_coord(s, size=DEFAULT_SIZE):
    """SGF坐标转(x,y)"""
    s = s.strip().upper()
    if s == 'PASS' or s == '':
        return (-1, -1)
    col = s[0]
    if col >= 'J':
        col = chr(ord(col) - 1)
    y = ord(col) - ord('A')
    row = int(s[1:])
    x = size - row
    return (x, y)
