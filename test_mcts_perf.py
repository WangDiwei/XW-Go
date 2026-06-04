"""性能对比测试 - 调试版"""
import time
import sys
print('[1] 启动', flush=True)
sys.path.insert(0, 'd:\\Learning\\XW_PROJECT\\XW-GO')
print('[2] 导入', flush=True)
from go_engine import GoBoard, BLACK
from ai_player import SimpleMCTS
print('[3] 创建棋盘', flush=True)
b = GoBoard(9)
for x, y in [(4, 4), (3, 3)]:
    b.play_move(x, y, BLACK)

print('[4] 串行MCTS (1模拟)', flush=True)
mcts1 = SimpleMCTS(simulations=1, parallel=False)
start = time.time()
mv1 = mcts1.select_move(b, BLACK)
t1 = time.time() - start
print(f'  结果: {mv1}, 耗时: {t1:.2f}s', flush=True)

print('[5] 并行MCTS (1模拟)', flush=True)
mcts2 = SimpleMCTS(simulations=1, parallel=True)
start = time.time()
mv2 = mcts2.select_move(b, BLACK)
t2 = time.time() - start
print(f'  结果: {mv2}, 耗时: {t2:.2f}s', flush=True)

print(f'加速比: {t1/t2:.2f}x', flush=True)
print('=' * 60, flush=True)

