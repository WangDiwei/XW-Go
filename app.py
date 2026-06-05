"""
XW-GO 围棋自对弈训练系统 - Flask后端
提供围棋规则、AI决策、自对弈训练、胜负判定与棋局分析的REST API
"""
import os
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

from go_engine import GoBoard, BLACK, WHITE, EMPTY, KOMI, coord_to_str, str_to_coord
from ai_player import GoAI, SimpleMCTS
from trainer import SelfPlayTrainer, DEFAULT_SIZE
import hardware

# 启动时硬件检测
print('=' * 60)
print('  正在检测硬件加速...')
print('=' * 60)
hardware.detect_all()
hardware.set_thread_env()
HW = hardware.get_info()
print(f'  CPU: {HW["cpu"]} ({HW["cores"]}核)')
for g in HW['gpus']:
    extra = ''
    if 'memory_gb' in g:
        extra = f' [{g["memory_gb"]}GB]'
    elif 'device' in g:
        extra = f' [{g["device"]}]'
    print(f'  GPU: {g["type"]} - {g["name"]}{extra}')
for n in HW['npus']:
    vendor = n.get('vendor', '')
    fw = n.get('framework', '')
    extra = f' [{fw}]' if fw else ''
    print(f'  NPU: {n["type"]} - {n["name"]}{extra} (vendor: {vendor})')
print(f'  加速后端: {HW["backend"]} ({HW["backend_detail"]})')
print('=' * 60)

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# 全局状态
BOARD_SIZE = DEFAULT_SIZE
trainer = SelfPlayTrainer(size=BOARD_SIZE, random_phase=1000)
trainer_lock = threading.Lock()

# 当前对局（人类/AI共享）
current_game = {
    'board': GoBoard(BOARD_SIZE),
    'mode': 'human_ai',  # human_ai | ai_ai | ai_ai_step
    'human_color': BLACK,  # 人类执黑
    'ai_thinking': False,
}


# ============ 工具函数 ============
def color_name(c):
    return {BLACK: '黑', WHITE: '白', 0: '和', EMPTY: '空'}.get(c, '?')


def new_game(size=BOARD_SIZE, mode='human_ai', human_color=BLACK):
    """开始新对局"""
    global current_game, BOARD_SIZE
    BOARD_SIZE = size
    b = GoBoard(size)
    current_game = {
        'board': b,
        'mode': mode,
        'human_color': human_color,
        'ai_thinking': False,
    }
    return b


def get_state_response(extra=None):
    """通用状态返回"""
    b = current_game['board']
    score = b.calculate_score() if b.is_game_over() else None
    data = {
        'size': b.size,
        'board': b.board,
        'pass_count': b.pass_count,
        'resigned': b.resigned,
        'last_move': b.last_move,
        'ko_point': b.ko_point,
        'move_count': len(b.move_history),
        'game_over': b.is_game_over(),
        'score': score,
        'next_color': BLACK if len(b.move_history) % 2 == 0 else WHITE,
        'mode': current_game['mode'],
        'human_color': current_game['human_color'],
    }
    if extra:
        data.update(extra)
    return data


# ============ 页面 ============
@app.route('/')
def index():
    return render_template('index.html')


# ============ API: 走子 ============
@app.route('/api/move', methods=['POST'])
def api_move():
    """提交一步棋
    Body: {x, y, color, pass:bool}
    """
    data = request.get_json() or {}
    b = current_game['board']
    if b.is_game_over():
        return jsonify({'ok': False, 'error': '对局已结束'}), 400
    color = int(data.get('color', 0))
    is_pass = data.get('pass', False)
    if is_pass:
        x, y = -1, -1
    else:
        x = int(data.get('x', -1))
        y = int(data.get('y', -1))
    # 校验当前应执子方
    expected = BLACK if len(b.move_history) % 2 == 0 else WHITE
    if color != expected:
        return jsonify({'ok': False, 'error': f'当前应{color_name(expected)}方走子'}), 400
    result = b.play_move(x, y, color)
    # 终局
    if b.is_game_over():
        result['game_over'] = True
        result['score'] = b.calculate_score()
    return jsonify({'ok': result.get('ok', False),
                    'error': result.get('error'),
                    'captured': result.get('captured', []),
                    'pass': result.get('pass', False),
                    'state': get_state_response()})


# ============ API: AI 走子 ============
@app.route('/api/ai-move', methods=['POST', 'GET'])
def api_ai_move():
    """AI走一步
    Body: {color, exploration}  color不传则自动使用当前应执子方
    """
    data = request.get_json(silent=True) or {}
    b = current_game['board']
    if b.is_game_over():
        return jsonify({'ok': False, 'error': '对局已结束',
                        'state': get_state_response()})
    expected = BLACK if len(b.move_history) % 2 == 0 else WHITE
    color = int(data.get('color', expected))
    # 简单MCTS模式（可由前端选择）
    use_mcts = data.get('use_mcts', False)
    if use_mcts:
        mcts = SimpleMCTS(simulations=30)
        mv = mcts.select_move(b, color)
    else:
        mv = trainer.ai.select_move(b, color, exploration=0.05)
    if mv is None:
        return jsonify({'ok': False, 'error': '无可行落子'})
    result = b.play_move(mv[0], mv[1], color)
    extra = {
        'ai_move': {'x': mv[0], 'y': mv[1], 'color': color,
                    'coord': coord_to_str(mv[0], mv[1], b.size)}
    }
    if b.is_game_over():
        extra['game_over'] = True
        extra['score'] = b.calculate_score()
    return jsonify({'ok': result.get('ok', False),
                    'error': result.get('error'),
                    'captured': result.get('captured', []),
                    'state': get_state_response(extra)})


# ============ API: 重置对局 ============
@app.route('/api/reset', methods=['POST'])
def api_reset():
    data = request.get_json() or {}
    size = int(data.get('size', BOARD_SIZE))
    mode = data.get('mode', current_game.get('mode', 'human_ai'))
    human_color = int(data.get('human_color', current_game.get('human_color', BLACK)))
    new_game(size=size, mode=mode, human_color=human_color)
    return jsonify({'ok': True, 'state': get_state_response()})


# ============ API: 获取状态 ============
@app.route('/api/state', methods=['GET'])
def api_state():
    return jsonify(get_state_response())


# ============ API: 认输 ============
@app.route('/api/resign', methods=['POST'])
def api_resign():
    data = request.get_json() or {}
    color = int(data.get('color', BLACK))
    b = current_game['board']
    b.resign(color)
    score = b.calculate_score()
    return jsonify({'ok': True, 'state': get_state_response({
        'game_over': True, 'score': score
    })})


# ============ API: 棋局分析 ============
@app.route('/api/analyze', methods=['POST', 'GET'])
def api_analyze():
    """分析当前棋盘：死活、围空、胜负"""
    b = current_game['board']
    t = b.get_territory()
    score = b.calculate_score() if b.is_game_over() else None
    return jsonify({
        'ok': True,
        'territory': t,
        'score': score,
        'game_over': b.is_game_over(),
        'moves': b.get_move_list(),
        'pass_count': b.pass_count,
    })


# ============ API: 棋谱列表 ============
@app.route('/api/move-list', methods=['GET'])
def api_move_list():
    b = current_game['board']
    return jsonify({
        'ok': True,
        'moves': b.get_move_list(),
        'size': b.size,
    })


# ============ API: 训练一步（一局）============
@app.route('/api/train/step', methods=['POST'])
def api_train_step():
    """执行一局自对弈"""
    data = request.get_json() or {}
    save_sgf = data.get('save_sgf', False)
    with trainer_lock:
        result = trainer.play_one_game(save_sgf=save_sgf)
        trainer.save()
    return jsonify({'ok': True, 'result': result, 'stats': trainer.get_stats()})


# ============ API: 训练N局 ============
@app.route('/api/train/auto', methods=['POST'])
def api_train_auto():
    """异步执行N局自对弈，前端可轮询stats"""
    data = request.get_json() or {}
    n = int(data.get('n', 10))
    save_every = int(data.get('save_every', 10))
    exploration = float(data.get('exploration', 0.1))
    delay = float(data.get('delay', 0.0))
    if trainer.is_training:
        return jsonify({'ok': False, 'error': '训练已在进行中'})
    def run():
        trainer.train_n_games(n, save_every=save_every, exploration=exploration, delay=delay)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return jsonify({'ok': True, 'message': f'已启动 {n} 局训练', 'n': n})


# ============ API: 停止训练 ============
@app.route('/api/train/stop', methods=['POST'])
def api_train_stop():
    trainer.stop()
    return jsonify({'ok': True, 'is_training': trainer.is_training})


# ============ API: 训练统计 ============
@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = trainer.get_stats()
    # 胜率曲线
    history = trainer.history[-100:]
    winrate_series = []
    last10_black = 0
    last10_white = 0
    last10_total = 0
    for h in history:
        if h['winner'] == BLACK:
            last10_black += 1
        elif h['winner'] == WHITE:
            last10_white += 1
        last10_total += 1
    stats['history_sample'] = history[-30:]  # 最近的局
    return jsonify(stats)


# ============ API: 硬件信息 ============
@app.route('/api/hardware', methods=['GET'])
def api_hardware():
    """返回硬件检测结果与当前加速后端"""
    info = hardware.get_info()
    # 加入线程库配置
    info['thread_env'] = {
        'OMP_NUM_THREADS': os.environ.get('OMP_NUM_THREADS', ''),
        'MKL_NUM_THREADS': os.environ.get('MKL_NUM_THREADS', ''),
        'OPENBLAS_NUM_THREADS': os.environ.get('OPENBLAS_NUM_THREADS', ''),
    }
    return jsonify(info)


# ============ API: 重新检测硬件 ============
@app.route('/api/hardware/refresh', methods=['POST'])
def api_hardware_refresh():
    """重新检测硬件（用于运行时插拔GPU等场景）"""
    hardware.detect_all()
    hardware.set_thread_env()
    return jsonify({'ok': True, 'info': hardware.get_info()})


# ============ API: 训练历史曲线 ============
@app.route('/api/stats/history', methods=['GET'])
def api_stats_history():
    """返回训练历史：每局胜负"""
    limit = int(request.args.get('limit', 200))
    history = trainer.history[-limit:]
    series = {
        'game_no': [h['game_no'] for h in history],
        'winner': [h['winner'] for h in history],
        'moves': [h['moves'] for h in history],
        'black_total': [h.get('black_total') for h in history],
        'white_total': [h.get('white_total') for h in history],
    }
    # 滑动窗口胜率
    winrates = []
    window = 20
    for i in range(len(history)):
        start = max(0, i - window + 1)
        sub = history[start:i+1]
        bw = sum(1 for h in sub if h['winner'] == BLACK)
        winrates.append(bw / len(sub) if sub else 0.5)
    series['winrate_black_smoothed'] = winrates
    return jsonify(series)


# ============ API: 保存棋谱 SGF ============
@app.route('/api/save-sgf', methods=['POST'])
def api_save_sgf():
    """保存当前对局为SGF"""
    b = current_game['board']
    moves = b.get_move_list()
    score = b.calculate_score() if b.is_game_over() else None
    sgf = _to_sgf(b, moves, score)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f"manual_game_{ts}.sgf"
    path = os.path.join(trainer.games_dir, fname)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(sgf)
        return jsonify({'ok': True, 'path': path, 'filename': fname})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/games', methods=['GET'])
def api_list_games():
    """列出已保存的棋谱"""
    files = []
    if os.path.exists(trainer.games_dir):
        for f in sorted(os.listdir(trainer.games_dir), reverse=True)[:50]:
            fp = os.path.join(trainer.games_dir, f)
            if os.path.isfile(fp):
                files.append({
                    'name': f,
                    'size': os.path.getsize(fp),
                    'mtime': os.path.getmtime(fp),
                })
    return jsonify({'ok': True, 'games': files})


@app.route('/api/games/<filename>', methods=['GET'])
def api_get_game(filename):
    """获取棋谱内容"""
    # 安全检查
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'ok': False, 'error': '非法文件名'}), 400
    path = os.path.join(trainer.games_dir, filename)
    if not os.path.exists(path):
        return jsonify({'ok': False, 'error': '文件不存在'}), 404
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({'ok': True, 'content': content, 'filename': filename})


def _to_sgf(board, moves, score):
    """生成SGF字符串"""
    lines = [f"(;SZ[{board.size}]KM[{KOMI}]"]
    for m in moves:
        color = 'B' if m['color'] == BLACK else 'W'
        if m.get('pass'):
            lines.append(f";{color}[]")
        else:
            s = coord_to_str(m['x'], m['y'], board.size)
            lines.append(f";{color}[{s}]")
    if score:
        winner = 'B' if score.get('winner') == BLACK else ('W' if score.get('winner') == WHITE else '0')
        lines.append(f";RE[{winner}+{score.get('margin', 0):.2f}]")
    lines.append(")")
    return '\n'.join(lines)


# ============ API: 切换 AI 模式 ============
@app.route('/api/ai-mode', methods=['POST'])
def api_ai_mode():
    """切换AI难度/模式（仅记录在trainer.ai上）"""
    data = request.get_json() or {}
    mode = data.get('mode', 'qtable')  # 'qtable' | 'mcts' | 'random'
    if 'random_phase' in data:
        trainer.ai.random_phase = int(data['random_phase'])
    return jsonify({'ok': True, 'mode': mode, 'random_phase': trainer.ai.random_phase})


# ============ API: 重置经验表（重新训练）============
@app.route('/api/train/reset', methods=['POST'])
def api_train_reset():
    """清空经验表和历史，重新开始训练"""
    global trainer
    trainer = SelfPlayTrainer(size=BOARD_SIZE, random_phase=1000)
    return jsonify({'ok': True, 'message': '已重置训练数据', 'stats': trainer.get_stats()})


# ============ 错误处理 ============
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return render_template('index.html')


if __name__ == '__main__':
    print("=" * 60)
    print("  XW-GO 围棋自对弈训练AI系统")
    print("=" * 60)
    print(f"棋盘尺寸: {BOARD_SIZE}x{BOARD_SIZE}")
    print(f"贴子: 黑贴{KOMI}子 (中国规则)")
    print(f"随机阶段: 前{trainer.ai.random_phase}局")
    print("访问: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
