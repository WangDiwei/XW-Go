"""
AI决策引擎 - 模仿AlphaGo自对弈的简化版本
阶段1 (前N局): 随机落子
阶段2 (之后): 基于经验表(state_hash -> (wins, visits))的UCB1选择
"""
import math
import random
import json
import os
from copy import deepcopy
from go_engine import GoBoard, BLACK, WHITE, EMPTY, KOMI


# 默认随机阶段局数
DEFAULT_RANDOM_PHASE = 1000
EXPLORATION_C = 1.4  # UCB1探索系数


class GoAI:
    """围棋AI - 简化版AlphaGo自对弈"""

    def __init__(self, ai_id="default"):
        self.ai_id = ai_id
        # 经验表: state_hash -> {next_state_hash: (wins, visits)}
        # 即当前状态下，走某一步后到达的新状态的价值
        self.q_table = {}  # 状态->动作的价值表
        # 全局访问计数
        self.total_visits = 0
        # 训练阶段
        self.total_games = 0
        self.random_phase = DEFAULT_RANDOM_PHASE

    def in_random_phase(self):
        """是否还在随机阶段"""
        return self.total_games < self.random_phase

    def select_move(self, board, color, exploration=0.1, temperature=1.0):
        """选择下一步
        Args:
            board: 当前棋盘
            color: 执子颜色
            exploration: 探索概率（学习阶段偶尔随机）
            temperature: 温度参数（控制选择锐度）
        Returns:
            (x, y) 或 (-1, -1) 表示pass
        """
        legal = board.get_legal_moves(color, include_pass=True)
        if not legal:
            return (-1, -1)
        # 随机阶段 + 探索概率 -> 随机
        if self.in_random_phase() or random.random() < exploration:
            return random.choice(legal)
        # 学习阶段：UCB1选择
        return self._ucb_select(board, color, legal, temperature)

    def _ucb_select(self, board, color, legal_moves, temperature=1.0):
        """UCB1选择"""
        state_hash = board.get_state_hash(color)
        # 初始化该状态的价值表
        if state_hash not in self.q_table:
            self.q_table[state_hash] = {}
        q = self.q_table[state_hash]
        # 统计该状态总访问次数
        state_visits = sum(v[1] for v in q.values()) + 1
        best_score = -float('inf')
        best_move = None
        for mv in legal_moves:
            next_hash = self._next_state_hash(board, color, mv)
            wins, visits = q.get(next_hash, (0.0, 0))
            if visits == 0:
                # 未访问过的走法，优先
                ucb = float('inf')
            else:
                win_rate = wins / visits
                ucb = win_rate + EXPLORATION_C * math.sqrt(math.log(state_visits) / visits)
            if ucb > best_score:
                best_score = ucb
                best_move = mv
        if best_move is None:
            best_move = random.choice(legal_moves)
        return best_move

    def _next_state_hash(self, board, color, move):
        """计算在某状态下走move后的状态哈希"""
        clone = board.clone()
        clone.play_move(move[0], move[1], color)
        next_color = WHITE if color == BLACK else BLACK
        return clone.get_state_hash(next_color)

    def record_path(self, path_states, winner_color):
        """根据对局结果更新路径上所有状态的胜率
        path_states: [(state_hash_before_move, next_state_hash_after_move, mover_color), ...]
        winner_color: 胜方 BLACK/WHITE/0(和棋)
        """
        for state_hash, next_hash, mover_color in path_states:
            if state_hash not in self.q_table:
                self.q_table[state_hash] = {}
            entry = self.q_table[state_hash].get(next_hash)
            if entry is None or not isinstance(entry, list):
                self.q_table[state_hash][next_hash] = [0.0, 0]
                entry = self.q_table[state_hash][next_hash]
            entry[1] += 1  # 访问+1
            if winner_color == 0:
                entry[0] += 0.5  # 和棋记0.5
            elif mover_color == winner_color:
                entry[0] += 1.0  # 胜方走的步记1
            # 败方不更新胜场
            self.total_visits += 1

    def save(self, path):
        """保存经验表"""
        # 转list方便JSON序列化
        serializable = {}
        for k, v in self.q_table.items():
            serializable[k] = {nk: [wins, visits] for nk, (wins, visits) in v.items()}
        data = {
            'q_table': serializable,
            'total_visits': self.total_visits,
            'total_games': self.total_games,
            'random_phase': self.random_phase,
            'ai_id': self.ai_id,
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path):
        """加载经验表"""
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.q_table = {}
            for k, v in data.get('q_table', {}).items():
                self.q_table[k] = {nk: list(wv) for nk, wv in v.items()}
            self.total_visits = data.get('total_visits', 0)
            self.total_games = data.get('total_games', 0)
            self.random_phase = data.get('random_phase', DEFAULT_RANDOM_PHASE)
            return True
        except Exception as e:
            print(f"加载经验表失败: {e}")
            return False

    def get_stats(self):
        """获取统计信息"""
        return {
            'ai_id': self.ai_id,
            'total_games': self.total_games,
            'total_visits': self.total_visits,
            'q_states': len(self.q_table),
            'random_phase': self.random_phase,
            'phase': 'random' if self.in_random_phase() else 'learning',
        }


class SimpleMCTS:
    """简化版MCTS - 用于对比实验
    通过 hardware 模块自动启用多线程并行模拟。
    """
    def __init__(self, simulations=50, parallel=True):
        self.simulations = simulations
        self.parallel = parallel
        self._pool = None
        try:
            import hardware
            self._backend = hardware.get_backend()
            self._cores = hardware.get_info().get('cores', 1)
        except Exception:
            self._backend = 'cpu'
            self._cores = 1

    def select_move(self, board, color):
        legal = board.get_legal_moves(color, include_pass=True)
        if not legal:
            return (-1, -1)
        if len(legal) == 1:
            return legal[0]

        if self.parallel and self._cores > 1:
            return self._select_parallel(board, color, legal)
        return self._select_serial(board, color, legal)

    def _select_serial(self, board, color, legal):
        best_move = None
        best_wins = -1
        for mv in legal:
            wins = 0
            for _ in range(self.simulations):
                winner = self._simulate(board, color, mv)
                if winner == color:
                    wins += 1
            if wins > best_wins:
                best_wins = wins
                best_move = mv
        return best_move

    def _select_parallel(self, board, color, legal):
        """多线程并行评估所有候选走法
        注意：所有线程共享同一 board，但每次模拟会调用 board.clone()，
        Python GIL 保证每个 clone/play_move 原子性，从而避免竞态。
        """
        from concurrent.futures import ThreadPoolExecutor
        sims_per_move = max(1, self.simulations)
        n_workers = min(self._cores, len(legal) * 2)
        # 准备任务：每个 (move_index, move) 对应所有模拟
        tasks = []
        for i, mv in enumerate(legal):
            for _ in range(sims_per_move):
                tasks.append((i, mv))

        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            results = list(ex.map(lambda t: (t[0], self._simulate(board, color, t[1])), tasks))

        # 汇总
        scores = [0] * len(legal)
        wins = [0] * len(legal)
        for idx, winner in results:
            wins[idx] += 1
            if winner == color:
                scores[idx] += 1

        best_idx = 0
        best_score = -1
        for i, s in enumerate(scores):
            if s > best_score:
                best_score = s
                best_idx = i
        return legal[best_idx]

    def _simulate_batch(self, board, color, first_move, count):
        """对单次首步执行 count 次模拟，返回赢的次数"""
        wins = 0
        for _ in range(count):
            winner = self._simulate(board, color, first_move)
            if winner == color:
                wins += 1
        return wins

    def _simulate(self, board, color, first_move):
        """从first_move开始，随机走子直到终局"""
        clone = board.clone()
        r = clone.play_move(first_move[0], first_move[1], color)
        if not r['ok']:
            return 0
        cur = WHITE if color == BLACK else BLACK
        max_steps = 200
        steps = 0
        while not clone.is_game_over() and steps < max_steps:
            legal = clone.get_legal_moves(cur, include_pass=True)
            if not legal:
                break
            mv = random.choice(legal)
            r = clone.play_move(mv[0], mv[1], cur)
            if not r['ok']:
                break
            cur = WHITE if cur == BLACK else BLACK
            steps += 1
        score = clone.calculate_score()
        return score.get('winner', 0)
