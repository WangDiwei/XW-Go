"""
自对弈训练循环
- 初始化：total_games = 0
- 前N局：随机落子
- 第N+1局起：自对弈学习（Q表+UCB）
- 每一局结束：回溯更新路径上的胜率
- 支持断点续训和棋谱保存
"""
import os
import json
import time
import threading
from datetime import datetime
from go_engine import GoBoard, BLACK, WHITE, EMPTY, KOMI
from ai_player import GoAI


# 默认参数
DEFAULT_SIZE = 9
DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
DEFAULT_GAMES_DIR = os.path.join(os.path.dirname(__file__), 'games')
MAX_MOVES_PER_GAME = 400  # 防止无限循环


class SelfPlayTrainer:
    """自对弈训练器"""

    def __init__(self, size=DEFAULT_SIZE, model_dir=DEFAULT_MODEL_DIR,
                 games_dir=DEFAULT_GAMES_DIR, random_phase=1000):
        self.size = size
        self.model_dir = model_dir
        self.games_dir = games_dir
        self.ai = GoAI(ai_id=f"xw_go_{size}x{size}")
        self.ai.random_phase = random_phase
        # 训练统计
        self.history = []  # 每局结果 [(game_no, winner, moves, black_score, white_score)]
        self.is_training = False
        self.stop_flag = False
        self.lock = threading.Lock()
        # 加载已有模型
        self._ensure_dirs()
        self._load_if_exists()

    def _ensure_dirs(self):
        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.games_dir, exist_ok=True)

    def _model_path(self):
        return os.path.join(self.model_dir, f'ai_{self.size}x{self.size}.json')

    def _stats_path(self):
        return os.path.join(self.model_dir, f'stats_{self.size}x{self.size}.json')

    def _load_if_exists(self):
        path = self._model_path()
        if self.ai.load(path):
            print(f"已加载模型: {path} (games={self.ai.total_games})")
        else:
            print(f"未找到已有模型，从头开始")
        # 加载统计
        sp = self._stats_path()
        if os.path.exists(sp):
            try:
                with open(sp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.history = data.get('history', [])
            except Exception as e:
                print(f"加载统计失败: {e}")

    def save(self):
        """保存模型和统计"""
        self.ai.save(self._model_path())
        with open(self._stats_path(), 'w', encoding='utf-8') as f:
            json.dump({'history': self.history[-2000:]}, f, ensure_ascii=False, indent=2)

    def play_one_game(self, save_sgf=False, exploration=0.1):
        """进行一局自对弈
        Returns: dict 包含对局结果
        """
        board = GoBoard(self.size)
        cur = BLACK
        path = []  # 记录每步的状态转移
        moves = []
        max_moves = MAX_MOVES_PER_GAME
        move_count = 0
        last_was_pass = False
        pass_count = 0

        while move_count < max_moves:
            # 终局
            if board.is_game_over():
                break
            # 选步
            mv = self.ai.select_move(board, cur, exploration=exploration)
            state_hash = board.get_state_hash(cur)
            # 执行
            result = board.play_move(mv[0], mv[1], cur)
            if not result['ok']:
                # 非法：尝试随机一步
                legal = board.get_legal_moves(cur, include_pass=True)
                if not legal:
                    break
                mv = __import__('random').choice(legal)
                result = board.play_move(mv[0], mv[1], cur)
                if not result['ok']:
                    break
            # 记录路径
            next_color = WHITE if cur == BLACK else BLACK
            next_hash = board.get_state_hash(next_color)
            path.append((state_hash, next_hash, cur))
            moves.append({
                'move_no': move_count + 1,
                'color': cur,
                'x': mv[0],
                'y': mv[1],
                'pass': result.get('pass', False),
                'captured': result.get('captured', []),
            })
            # 检查连续pass
            if result.get('pass'):
                pass_count += 1
                if pass_count >= 2:
                    break
            else:
                pass_count = 0
            cur = next_color
            move_count += 1

        # 终局
        score = board.calculate_score()
        winner = score.get('winner', 0)
        # 更新经验
        with self.lock:
            self.ai.record_path(path, winner)
            self.ai.total_games += 1
            self.history.append({
                'game_no': self.ai.total_games,
                'winner': winner,
                'moves': move_count,
                'black_total': score.get('black_total'),
                'white_total': score.get('white_total'),
                'reason': score.get('reason', '终局'),
                'timestamp': datetime.now().isoformat(),
            })
        # 保存棋谱
        if save_sgf:
            self._save_game_sgf(moves, winner, score)
        return {
            'game_no': self.ai.total_games,
            'winner': winner,
            'moves': move_count,
            'black_total': score.get('black_total'),
            'white_total': score.get('white_total'),
            'margin': score.get('margin'),
            'reason': score.get('reason'),
        }

    def _save_game_sgf(self, moves, winner, score):
        """保存为SGF格式"""
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f"game_{self.ai.total_games:06d}_{ts}.sgf"
        path = os.path.join(self.games_dir, fname)
        sgf = self._to_sgf(moves, winner, score)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(sgf)
        except Exception as e:
            print(f"保存SGF失败: {e}")

    def _to_sgf(self, moves, winner, score):
        """转换为SGF格式"""
        from go_engine import coord_to_str
        lines = [f"(;SZ[{self.size}]KM[{KOMI}]"]
        for m in moves:
            color = 'B' if m['color'] == BLACK else 'W'
            if m['pass']:
                lines.append(f";{color}[]")
            else:
                s = coord_to_str(m['x'], m['y'], self.size)
                lines.append(f";{color}[{s}]")
        lines.append(")")
        return '\n'.join(lines)

    def train_n_games(self, n, save_every=10, exploration=0.1, callback=None,
                      delay=0.0):
        """连续训练N局
        callback: 每局后调用，参数为该局结果
        """
        self.is_training = True
        self.stop_flag = False
        for i in range(n):
            if self.stop_flag:
                break
            result = self.play_one_game(save_sgf=False, exploration=exploration)
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    print(f"回调失败: {e}")
            if (i + 1) % save_every == 0:
                self.save()
            if delay > 0:
                time.sleep(delay)
        self.save()
        self.is_training = False
        return self.history[-n:] if n <= len(self.history) else list(self.history)

    def stop(self):
        self.stop_flag = True

    def get_winrate(self, last_n=10):
        """获取最近N局黑棋胜率"""
        if not self.history:
            return 0.5
        recent = self.history[-last_n:]
        if not recent:
            return 0.5
        black_wins = sum(1 for h in recent if h['winner'] == BLACK)
        return black_wins / len(recent)

    def get_stats(self):
        """获取总体训练统计"""
        recent = self.history[-10:]
        black_wins = sum(1 for h in recent if h['winner'] == BLACK)
        white_wins = sum(1 for h in recent if h['winner'] == WHITE)
        draws = sum(1 for h in recent if h['winner'] == 0)
        # 总胜率
        all_black = sum(1 for h in self.history if h['winner'] == BLACK)
        all_white = sum(1 for h in self.history if h['winner'] == WHITE)
        total = max(1, len(self.history))
        return {
            'total_games': self.ai.total_games,
            'total_visits': self.ai.total_visits,
            'q_states': len(self.ai.q_table),
            'random_phase': self.ai.random_phase,
            'phase': 'random' if self.ai.in_random_phase() else 'learning',
            'is_training': self.is_training,
            'winrate_black_last10': black_wins / max(1, len(recent)),
            'winrate_white_last10': white_wins / max(1, len(recent)),
            'draws_last10': draws,
            'winrate_black_all': all_black / total,
            'winrate_white_all': all_white / total,
            'history_length': len(self.history),
            'size': self.size,
        }


# 自测
if __name__ == '__main__':
    t = SelfPlayTrainer(size=9, random_phase=10)
    print("开始训练 5 局自对弈...")
    results = t.train_n_games(5, save_every=2, delay=0)
    for r in results:
        winner_str = {BLACK: '黑胜', WHITE: '白胜', 0: '和棋'}.get(r['winner'], '?')
        print(f"  第{r['game_no']}局: {winner_str}, {r['moves']}手, "
              f"黑{r['black_total']:.2f} 白{r['white_total']:.2f}")
    print("统计:", t.get_stats())
    t.save()
