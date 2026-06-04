# XW-GO 围棋自对弈训练AI

一个基于 Python + Flask + HTML/Canvas 的围棋自对弈训练AI系统，模仿 AlphaGo 的自对弈学习流程，重点展示完整对弈、胜负判定、局后分析与可视化训练。

## ✨ 特性

### 核心功能
- **完整围棋规则**（中国规则，黑贴 3.75 子）
  - 气的计算、提子、自杀保护
  - 禁着点判定、禁止全局同形（劫争）
  - 终局判定（双方连续虚着 / 一方认输）
  - 数子法胜负计算
- **AI 决策引擎**
  - 阶段一（前 N 局）：随机落子，探索棋盘
  - 阶段二（N+1 局起）：基于 Q 表 + UCB1 的自对弈学习
  - 简单 MCTS 模式可对比
- **自对弈训练循环**
  - 异步连续训练 N 局
  - 实时统计：总对局数、阶段、近 N 局胜率、Q 表状态数
  - 模型自动保存到 `models/`
  - 棋谱 SGF 自动保存到 `games/`
- **REST API**：走子、AI 走子、重置、分析、训练、SGF 保存/加载

### 前端（深色专业围棋软件风格）
- 19×19 / 13×13 / 9×9 木质棋盘
- 棋子渐变 + 高光 + 落子动画
- 终局自动弹窗（胜负、子数、围空、差值）
- 棋谱列表 / 训练曲线（Chart.js）
- 玻璃拟态控制面板
- 热键：空格=AI走一步，P=虚着，R=重置，N=新对局，A=分析

## 📦 项目结构

```
XW-GO/
├── go_engine.py        # 围棋规则引擎
├── ai_player.py        # AI 决策（Q表+UCB1 / 简单MCTS）
├── trainer.py          # 自对弈训练循环
├── app.py              # Flask 后端 + REST API
├── requirements.txt    # Python 依赖
├── README.md
├── templates/
│   └── index.html      # 主页面
├── static/
│   ├── css/style.css   # 样式（木质+深色主题）
│   └── js/main.js      # 前端逻辑（Canvas 棋盘+Chart.js）
├── models/             # AI 模型（自动创建）
│   ├── ai_9x9.json     # 经验表
│   └── stats_9x9.json  # 训练历史
└── games/              # SGF 棋谱
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> 需要 Python 3.8+（推荐 3.10+），依赖只有 Flask 和 Flask-CORS。

### 2. 启动后端

```bash
python app.py
```

输出：
```
============================================================
  XW-GO 围棋自对弈训练AI系统
============================================================
棋盘尺寸: 9x9
贴子: 黑贴3.75子 (中国规则)
随机阶段: 前1000局
访问: http://localhost:5000
============================================================
```

### 3. 打开前端

浏览器访问 [http://localhost:5000](http://localhost:5000)

## 🎮 使用指南

### 对局模式
- **人类 vs AI**：默认模式，AI 自动执白棋（黑先白后）
- **AI 单步**：AI vs AI，点击 "AI 走一步" 推进
- **AI 连续**：AI vs AI 连续自动下，每步间隔 0.6s
- **自对弈训练**：连续 N 局 AI 自对弈，自动更新 Q 表

### 训练流程
1. 选择 "每批局数"（如 10 / 100）
2. 点击 "🚀 开始训练"，AI 将在后台自动连续对弈
3. 训练数据自动保存到 `models/`
4. 胜率曲线实时更新
5. 阶段二（>1000 局）后 AI 将基于 Q 表+UCB1 选择走法

### 棋局分析
点击 "🔍 请求分析" 获取：
- 双方子数、围空、总数
- 胜负判定（需终局）
- 棋谱摘要

### 棋谱保存/加载
- 点击 "💾 保存棋谱" 保存当前对局为 SGF
- 通过 `GET /api/games` 列出已保存棋谱

## 🔌 API 端点

| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/api/state` | 获取当前对局状态 |
| POST | `/api/move` | 提交落子 `{x, y, color}` 或 `{pass:true}` |
| POST | `/api/ai-move` | AI 走一步 |
| POST | `/api/reset` | 重置对局 |
| POST | `/api/resign` | 认输 |
| POST | `/api/analyze` | 分析棋局 |
| GET | `/api/move-list` | 棋谱列表 |
| POST | `/api/train/step` | 训练 1 局 |
| POST | `/api/train/auto` | 训练 N 局（异步） |
| POST | `/api/train/stop` | 停止训练 |
| GET | `/api/stats` | 训练统计 |
| GET | `/api/stats/history?limit=N` | 历史曲线 |
| POST | `/api/save-sgf` | 保存 SGF |
| GET | `/api/games` | 棋谱列表 |
| GET | `/api/games/{filename}` | 获取棋谱内容 |
| POST | `/api/ai-mode` | 切换 AI 模式 |

## ⚙️ 关键参数

`app.py` 中可调：
- `BOARD_SIZE = 9` — 默认棋盘大小
- `trainer.ai.random_phase = 1000` — 随机阶段局数

`go_engine.py`：
- `KOMI = 3.75` — 黑方贴子（中国规则）

`ai_player.py`：
- `EXPLORATION_C = 1.4` — UCB1 探索系数

## 🧪 单元测试

```bash
python test_engine.py
```

覆盖：基本走子、提子、自杀保护、虚着、终局、胜负计算、坐标转换。

## 📜 规则实现说明

严格遵循 `围棋规则.txt`：
- 棋子的气 → BFS 找连通块
- 提子 → 下子后立即提对方无气之子
- 禁着点 → 自杀（己方无气且不能提对方）禁止
- 禁止全局同形 → 记录 `state_hash`，重复局面拒绝
- 终局 → 双方连续虚着 / 一方认输
- 数子法 → 黑总数 = 黑子 + 黑围空；白总数 = 白子 + 白围空 + 3.75

## 🛠️ 技术栈

- **后端**：Flask 3.x, Flask-CORS
- **前端**：HTML5 Canvas, Chart.js 4
- **AI**：UCB1 + Q 表（自对弈学习）
- **存储**：JSON（经验表 + 训练历史）

## 📝 License

MIT
