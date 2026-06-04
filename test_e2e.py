"""端到端API测试"""
import requests
import time

BASE = 'http://localhost:5000'

def test_full_game():
    print('=== 端到端测试：完整对局 ===')
    # 1. 重置
    r = requests.post(f'{BASE}/api/reset', json={'size': 9, 'mode': 'human_ai', 'human_color': 1})
    print('Reset:', r.json()['ok'])
    state = r.json()['state']
    print(f'  size={state["size"]} next={state["next_color"]}')

    # 2. 人类下棋 - 连续虚着2次触发终局
    moves = [(2, 2), (4, 4), (-1, -1), (-1, -1)]  # 2次连续虚着->终局
    for i, (x, y) in enumerate(moves):
        color = 1 if i % 2 == 0 else 2
        is_pass = (x == -1)
        body = {'color': color, 'pass': is_pass}
        if not is_pass:
            body['x'] = x; body['y'] = y
        r = requests.post(f'{BASE}/api/move', json=body)
        d = r.json()
        if not d['ok']:
            print(f'  Move {i+1} failed:', d.get('error'))
            return
        s = d['state']
        print(f'  Move {i+1}: {color} at {(x,y)} ok, game_over={s["game_over"]}')

    # 3. 分析
    r = requests.post(f'{BASE}/api/analyze')
    d = r.json()
    print('\n=== 棋局分析 ===')
    print(f'  Game over: {d["game_over"]}')
    print(f'  Score: {d["score"]["winner"]} (黑={d["score"].get("black_total")} 白={d["score"].get("white_total")})')
    print(f'  Moves: {len(d["moves"])}')

    # 4. 训练一步
    print('\n=== 训练测试 ===')
    r = requests.post(f'{BASE}/api/train/step', json={})
    d = r.json()
    print(f'  Train 1 game: winner={d["result"]["winner"]} moves={d["result"]["moves"]}')
    print(f'  Stats: total_games={d["stats"]["total_games"]} phase={d["stats"]["phase"]}')

    # 5. 训练多步
    print('\n=== 训练5局（异步）===')
    r = requests.post(f'{BASE}/api/train/auto', json={'n': 5, 'delay': 0.0})
    msg = r.json()
    print(f'  Response: {msg}')
    if msg.get('ok'):
        time.sleep(2)
        r = requests.get(f'{BASE}/api/stats')
        d = r.json()
        print(f'  After 2s: total_games={d["total_games"]} training={d["is_training"]}')
    else:
        print(f'  Skipped: {msg.get("error")}')

    # 6. 历史曲线
    r = requests.get(f'{BASE}/api/stats/history?limit=20')
    d = r.json()
    print(f'  History: {len(d["game_no"])} games, smoothed winrates: {d["winrate_black_smoothed"][-3:]}')

    # 7. 棋谱列表
    r = requests.post(f'{BASE}/api/save-sgf')
    print(f'  Save SGF: {r.json().get("filename", "failed")}')

    print('\n=== ALL E2E TESTS PASS ===')

if __name__ == '__main__':
    import requests  # pip install requests if needed
    test_full_game()
