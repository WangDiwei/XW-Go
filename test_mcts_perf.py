"""性能对比测试：串行MCTS vs 并行MCTS"""
import time
import sys
sys.path.insert(0, 'd:\\Learning\\XW_PROJECT\\XW-GO')
from go_engine import GoBoard, BLACK
from ai_player import SimpleMCTS

print('=' * 60)
print('MCTS 性能测试（9x9 棋盘，50次模拟/走法）')
print('=' * 60)

# 准备一个有较多走子的棋局
b = GoBoard(9)
for x, y in [(4, 4), (3, 3), (5, 5), (4, 3), (5, 4)]:
    b.play_move(x, y, BLACK)

# 串行MCTS
print('\n[串行模式]')
mcts_serial = SimpleMCTS(simulations=20, parallel=False)
start = time.time()
mv = mcts_serial.select_move(b, BLACK)
t_serial = time.time() - start
print(f'  走法: {mv}  耗时: {t_serial:.2f}s')

# 并行MCTS
print('\n[并行模式 - 8线程]')
mcts_par = SimpleMCTS(simulations=20, parallel=True)
start = time.time()
mv = mcts_par.select_move(b, BLACK)
t_par = time.time() - start
print(f'  走法: {mv}  耗时: {t_par:.2f}s')

print(f'\n加速比: {t_serial / t_par:.2f}x')
print('=' * 60)
