/* XW-GO 围棋自对弈训练AI - 主前端脚本 */
'use strict';

// ========== 全局状态 ==========
const State = {
    size: 9,
    board: [],
    passCount: 0,
    lastMove: null,
    koPoint: null,
    moveCount: 0,
    gameOver: false,
    nextColor: 1, // 1=黑 2=白
    mode: 'human_ai', // human_ai | ai_ai_step | ai_ai | ai_selfplay
    humanColor: 1,
    isThinking: false,
    training: false,
    winrateChart: null,
    stoneRadius: 14,
    cellSize: 60,
    margin: 40,
    winrateHistory: [],
    autoPlayTimer: null,
    pollTimer: null,
};

// 颜色常量
const BLACK = 1;
const WHITE = 2;
const EMPTY = 0;

// ========== API 封装 ==========
const API = {
    async get(url) {
        const r = await fetch(url);
        return r.json();
    },
    async post(url, data) {
        const r = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data || {}),
        });
        return r.json();
    },
};

// ========== DOM 工具 ==========
const $ = (id) => document.getElementById(id);

function showToast(msg, type = 'info') {
    const t = $('toast');
    t.textContent = msg;
    t.className = 'toast show ' + type;
    setTimeout(() => {
        t.className = 'toast ' + type;
    }, 3000);
}

function coordToStr(x, y) {
    if (x === -1 && y === -1) return 'pass';
    const col = String.fromCharCode(65 + y);
    const realCol = col >= 'I' ? String.fromCharCode(col.charCodeAt(0) + 1) : col;
    return `${realCol}${State.size - x}`;
}

// ========== 棋盘绘制 ==========
function drawBoard() {
    const canvas = $('board');
    const size = State.size;
    const containerWidth = canvas.parentElement.clientWidth;
    const containerHeight = canvas.parentElement.clientHeight;
    const side = Math.min(containerWidth, containerHeight) - 16;
    canvas.width = side;
    canvas.height = side;
    canvas.style.width = side + 'px';
    canvas.style.height = side + 'px';

    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    State.margin = 30;
    State.cellSize = (W - 2 * State.margin) / (size - 1);
    State.stoneRadius = State.cellSize * 0.42;

    // 背景：木质纹理渐变
    const grad = ctx.createLinearGradient(0, 0, W, H);
    grad.addColorStop(0, '#DEB887');
    grad.addColorStop(0.5, '#D2A878');
    grad.addColorStop(1, '#B8895A');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    // 木纹细节
    ctx.save();
    ctx.globalAlpha = 0.06;
    ctx.strokeStyle = '#5C3A1E';
    ctx.lineWidth = 0.5;
    for (let i = 0; i < 30; i++) {
        ctx.beginPath();
        const y = Math.random() * H;
        ctx.moveTo(0, y);
        ctx.bezierCurveTo(W * 0.3, y + (Math.random() - 0.5) * 20,
                          W * 0.7, y + (Math.random() - 0.5) * 20,
                          W, y + (Math.random() - 0.5) * 10);
        ctx.stroke();
    }
    ctx.restore();

    // 边线
    ctx.strokeStyle = '#3E2723';
    ctx.lineWidth = 2;
    ctx.strokeRect(State.margin - 6, State.margin - 6,
                   State.cellSize * (size - 1) + 12, State.cellSize * (size - 1) + 12);

    // 内部网格线
    ctx.strokeStyle = '#3E2723';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < size; i++) {
        const p = State.margin + i * State.cellSize;
        ctx.moveTo(State.margin, p);
        ctx.lineTo(State.margin + (size - 1) * State.cellSize, p);
        ctx.moveTo(p, State.margin);
        ctx.lineTo(p, State.margin + (size - 1) * State.cellSize);
    }
    ctx.stroke();

    // 星标
    drawStarPoints(ctx, size);

    // 坐标标签 (A-T 跳过 I)
    ctx.fillStyle = '#3E2723';
    ctx.font = `${Math.max(10, State.cellSize * 0.25)}px "Microsoft YaHei", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < size; i++) {
        const p = State.margin + i * State.cellSize;
        // 顶部
        let col = String.fromCharCode(65 + i);
        if (col >= 'I') col = String.fromCharCode(col.charCodeAt(0) + 1);
        ctx.fillText(col, p, State.margin - 14);
        ctx.fillText(col, p, State.margin + (size - 1) * State.cellSize + 14);
        // 左侧
        const rowLabel = String(size - i);
        ctx.fillText(rowLabel, State.margin - 14, p);
        ctx.fillText(rowLabel, State.margin + (size - 1) * State.cellSize + 14, p);
    }

    // 绘制棋子
    for (let x = 0; x < size; x++) {
        for (let y = 0; y < size; y++) {
            const c = State.board[x] && State.board[x][y];
            if (c !== EMPTY) {
                drawStone(ctx, x, y, c,
                    State.lastMove && State.lastMove[0] === x && State.lastMove[1] === y);
            }
        }
    }

    // 劫点标记
    if (State.koPoint) {
        const [kx, ky] = State.koPoint;
        const px = State.margin + ky * State.cellSize;
        const py = State.margin + kx * State.cellSize;
        ctx.strokeStyle = '#D32F2F';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.arc(px, py, State.stoneRadius * 0.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
    }
}

function drawStarPoints(ctx, size) {
    // 天元和星位
    let stars;
    if (size === 9) {
        stars = [[2, 2], [2, 6], [4, 4], [6, 2], [6, 6]];
    } else if (size === 13) {
        stars = [[3, 3], [3, 9], [6, 6], [9, 3], [9, 9]];
    } else if (size === 19) {
        stars = [[3, 3], [3, 9], [3, 15], [9, 3], [9, 9], [9, 15], [15, 3], [15, 9], [15, 15]];
    } else {
        return;
    }
    ctx.fillStyle = '#3E2723';
    for (const [x, y] of stars) {
        const px = State.margin + y * State.cellSize;
        const py = State.margin + x * State.cellSize;
        ctx.beginPath();
        ctx.arc(px, py, 3.5, 0, Math.PI * 2);
        ctx.fill();
    }
}

function drawStone(ctx, x, y, color, isLast) {
    const px = State.margin + y * State.cellSize;
    const py = State.margin + x * State.cellSize;
    const r = State.stoneRadius;
    // 阴影
    ctx.save();
    ctx.shadowColor = 'rgba(0, 0, 0, 0.5)';
    ctx.shadowBlur = 6;
    ctx.shadowOffsetX = 1;
    ctx.shadowOffsetY = 2;
    if (color === BLACK) {
        const grad = ctx.createRadialGradient(
            px - r * 0.3, py - r * 0.3, r * 0.1,
            px, py, r);
        grad.addColorStop(0, '#666');
        grad.addColorStop(0.5, '#222');
        grad.addColorStop(1, '#000');
        ctx.fillStyle = grad;
    } else {
        const grad = ctx.createRadialGradient(
            px - r * 0.3, py - r * 0.3, r * 0.1,
            px, py, r);
        grad.addColorStop(0, '#ffffff');
        grad.addColorStop(0.7, '#e8e8e8');
        grad.addColorStop(1, '#b0b0b0');
        ctx.fillStyle = grad;
        ctx.strokeStyle = '#888';
        ctx.lineWidth = 0.5;
    }
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fill();
    if (color === WHITE) {
        ctx.stroke();
    }
    ctx.restore();
    // 最后一手标记
    if (isLast) {
        ctx.strokeStyle = color === BLACK ? '#FFD700' : '#D32F2F';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(px, py, r * 0.4, 0, Math.PI * 2);
        ctx.stroke();
    }
}

// ========== 点击落子 ==========
function setupBoardClick() {
    const canvas = $('board');
    canvas.addEventListener('click', async (e) => {
        if (State.isThinking) return;
        if (State.gameOver) return;
        // 人类 vs AI 模式下，AI 思考时不可点
        if (State.mode === 'human_ai' && State.nextColor !== State.humanColor) return;
        if (State.mode === 'ai_ai' || State.mode === 'ai_selfplay') return;

        const rect = canvas.getBoundingClientRect();
        const cx = e.clientX - rect.left;
        const cy = e.clientY - rect.top;
        const x = Math.round((cy - State.margin) / State.cellSize);
        const y = Math.round((cx - State.margin) / State.cellSize);
        if (x < 0 || x >= State.size || y < 0 || y >= State.size) return;
        await makeMove(x, y, State.nextColor);
    });
}

async function makeMove(x, y, color) {
    setThinking(true);
    try {
        const r = await API.post('/api/move', { x, y, color });
        if (!r.ok) {
            showToast(r.error || '非法落子', 'error');
            return false;
        }
        applyState(r.state);
        return true;
    } catch (e) {
        showToast('网络错误: ' + e.message, 'error');
        return false;
    } finally {
        setThinking(false);
    }
}

async function makePass(color) {
    setThinking(true);
    try {
        const r = await API.post('/api/move', { x: -1, y: -1, color, pass: true });
        if (!r.ok) {
            showToast(r.error || '虚着失败', 'error');
            return false;
        }
        applyState(r.state);
        return true;
    } finally {
        setThinking(false);
    }
}

async function aiMoveOnce() {
    setThinking(true);
    try {
        const r = await API.post('/api/ai-move', {});
        if (!r.ok) {
            showToast(r.error || 'AI无法走子', 'error');
            return false;
        }
        applyState(r.state);
        return true;
    } finally {
        setThinking(false);
    }
}

// ========== 状态应用 ==========
function applyState(s) {
    State.size = s.size || State.size;
    State.board = s.board || [];
    State.passCount = s.pass_count || 0;
    State.lastMove = s.last_move;
    State.koPoint = s.ko_point;
    State.moveCount = s.move_count || 0;
    State.gameOver = s.game_over;
    State.nextColor = s.next_color || 1;
    State.mode = s.mode || State.mode;
    State.humanColor = s.human_color || State.humanColor;

    // 更新UI
    $('moveCount').textContent = State.moveCount;
    $('passCount').textContent = State.passCount;
    $('boardSize').textContent = `${State.size}×${State.size}`;

    const turn = $('turnIndicator');
    if (State.gameOver) {
        turn.innerHTML = '<span class="stone-icon black"></span>已终局';
    } else {
        if (State.nextColor === BLACK) {
            turn.innerHTML = '<span class="stone-icon black"></span>黑方走子';
        } else {
            turn.innerHTML = '<span class="stone-icon white"></span>白方走子';
        }
    }

    drawBoard();
    updateMoveList();

    // 终局弹窗
    if (State.gameOver && s.score) {
        showGameOverModal(s.score);
    }
}

// ========== 棋谱列表 ==========
function updateMoveList() {
    const list = $('moveList');
    if (!State.board || State.moveCount === 0) {
        list.innerHTML = '<div class="move-empty">暂无落子</div>';
        return;
    }
    // 通过棋盘差量重建
    const items = [];
    for (let i = 0; i < State.moveCount; i++) {
        const color = (i % 2 === 0) ? BLACK : WHITE;
        const col = color === BLACK ? 'b' : 'w';
        items.push({ num: i + 1, color: col, value: '?' });
    }
    // 实际从后端获取完整棋谱
    API.get('/api/move-list').then((r) => {
        if (!r.ok) return;
        const moves = r.moves || [];
        const html = moves.map((m) => {
            const col = m.color === BLACK ? 'b' : 'w';
            const c = m.pass ? '虚着' : coordToStr(m.x, m.y);
            return `<div class="move-item">
                <span class="num">${m.index}.</span>
                <span class="color ${col}">${col === 'b' ? '●' : '○'}</span>
                <span class="coord">${c}</span>
            </div>`;
        }).join('');
        list.innerHTML = html || '<div class="move-empty">暂无落子</div>';
    });
}

// ========== 终局弹窗 ==========
function showGameOverModal(score) {
    const body = $('modalBody');
    const winnerText = score.winner === BLACK ? '⚫ 黑方胜' :
                       score.winner === WHITE ? '⚪ 白方胜' : '和棋';
    const reason = score.reason || '终局';
    const blackTotal = score.black_total != null ? score.black_total.toFixed(2) : '—';
    const whiteTotal = score.white_total != null ? score.white_total.toFixed(2) : '—';
    const margin = score.margin != null ? score.margin.toFixed(2) : '—';
    body.innerHTML = `
        <div class="winner">${winnerText}</div>
        <div class="stat-row"><span class="stat-label">终局原因</span><span class="stat-value">${reason}</span></div>
        <div class="stat-row"><span class="stat-label">黑方总数</span><span class="stat-value">${blackTotal}</span></div>
        <div class="stat-row"><span class="stat-label">白方总数(含贴子)</span><span class="stat-value">${whiteTotal}</span></div>
        <div class="stat-row"><span class="stat-label">胜负差</span><span class="stat-value">${margin} 子</span></div>
        ${score.black_stones != null ? `
        <div class="stat-row"><span class="stat-label">黑子数 / 黑围空</span><span class="stat-value">${score.black_stones} / ${score.black_territory}</span></div>
        <div class="stat-row"><span class="stat-label">白子数 / 白围空</span><span class="stat-value">${score.white_stones} / ${score.white_territory}</span></div>
        ` : ''}
        <div class="stat-row"><span class="stat-label">总手数</span><span class="stat-value">${State.moveCount}</span></div>
    `;
    $('gameOverModal').classList.add('active');
}

// ========== 训练统计 ==========
async function refreshStats() {
    const r = await API.get('/api/stats');
    if (!r || !r.ok && !r.total_games) {
        // 兼容两种格式
    }
    $('statTotalGames').textContent = r.total_games || 0;
    $('statPhase').textContent = r.phase === 'random' ? '随机阶段' : '学习阶段';
    $('statQStates').textContent = r.q_states || 0;
    $('statVisits').textContent = r.total_visits || 0;
    const bw = ((r.winrate_black_last10 || 0) * 100).toFixed(1) + '%';
    const ww = ((r.winrate_white_last10 || 0) * 100).toFixed(1) + '%';
    $('statBlackWinrate').textContent = bw;
    $('statWhiteWinrate').textContent = ww;
    State.training = r.is_training || false;
    // 训练中时显示进度
    if (State.training) {
        showToast('训练中...', 'success');
    }
}

async function refreshHistory() {
    const r = await API.get('/api/stats/history?limit=200');
    if (!r || !r.game_no) return;
    if (State.winrateChart) {
        State.winrateChart.data.labels = r.game_no;
        State.winrateChart.data.datasets[0].data = r.winrate_black_smoothed;
        State.winrateChart.update('none');
    } else {
        initWinrateChart(r);
    }
}

function initWinrateChart(data) {
    const ctx = $('winrateChart');
    State.winrateChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.game_no || [],
            datasets: [
                {
                    label: '黑胜率(滑动20局)',
                    data: data.winrate_black_smoothed || [],
                    borderColor: '#FFD700',
                    backgroundColor: 'rgba(255, 215, 0, 0.15)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                },
                {
                    label: '白胜率(滑动20局)',
                    data: (data.winrate_black_smoothed || []).map(v => 1 - v),
                    borderColor: '#4FC3F7',
                    backgroundColor: 'rgba(79, 195, 247, 0.1)',
                    borderWidth: 1.5,
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: {
                    labels: { color: '#cccccc', font: { size: 10 } }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    titleColor: '#FFD700',
                    bodyColor: '#fff',
                }
            },
            scales: {
                x: {
                    ticks: { color: '#888', font: { size: 9 }, maxTicksLimit: 8 },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: {
                    min: 0, max: 1,
                    ticks: { color: '#888', font: { size: 9 } },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
}

// ========== 棋局分析 ==========
async function requestAnalysis() {
    const r = await API.post('/api/analyze');
    if (!r.ok) {
        showToast('分析失败', 'error');
        return;
    }
    const out = $('analysisOutput');
    const lines = [];
    lines.push('<div class="analysis-line label">═══════ 棋局分析 ═══════</div>');
    lines.push(`<div class="analysis-line">棋盘尺寸: ${r.moves && r.moves.length ? State.size : State.size}×${State.size}</div>`);
    lines.push(`<div class="analysis-line">手数: ${(r.moves || []).length}</div>`);
    lines.push(`<div class="analysis-line">虚着数: ${r.pass_count || 0}</div>`);
    if (r.territory) {
        const t = r.territory;
        lines.push('<div class="analysis-line label">── 围空与子数 ──</div>');
        lines.push(`<div class="analysis-line value">黑: ${t.black_stones}子 + ${t.black_territory}空 = ${t.black_total}</div>`);
        lines.push(`<div class="analysis-line value">白: ${t.white_stones}子 + ${t.white_territory}空 + 3.75贴子 = ${t.white_total}</div>`);
    }
    if (r.score && r.score.ended) {
        const s = r.score;
        const winnerStr = s.winner === BLACK ? '黑胜' : s.winner === WHITE ? '白胜' : '和棋';
        lines.push('<div class="analysis-line label">── 胜负 ──</div>');
        lines.push(`<div class="analysis-line value" style="color:#FFD700">${winnerStr} (差 ${s.margin}子)</div>`);
        lines.push(`<div class="analysis-line">${s.reason}</div>`);
    } else {
        lines.push('<div class="analysis-line warn">对局未结束（连续虚着或认输时计算胜负）</div>');
    }
    lines.push('<div class="analysis-line label">── 棋谱摘要(最近10手) ──</div>');
    const moves = r.moves || [];
    const recent = moves.slice(-10);
    for (const m of recent) {
        const col = m.color === BLACK ? '●' : '○';
        const coord = m.pass ? '虚着' : coordToStr(m.x, m.y);
        lines.push(`<div class="analysis-line">${m.index}. ${col} ${coord}</div>`);
    }
    out.innerHTML = lines.join('');
    showToast('分析完成', 'success');
}

// ========== 控制函数 ==========
function setThinking(on) {
    State.isThinking = on;
    $('boardOverlay').classList.toggle('active', on);
}

async function newGame() {
    const size = parseInt($('boardSizeSelect').value);
    const humanColor = parseInt($('humanColorSelect').value);
    State.size = size;
    const r = await API.post('/api/reset', {
        size, mode: State.mode, human_color: humanColor
    });
    if (r.ok) {
        applyState(r.state);
        showToast('新对局开始', 'success');
        if (State.mode === 'human_ai' && humanColor === WHITE) {
            // AI执黑先手
            setTimeout(() => aiMoveOnce(), 400);
        }
    }
}

async function resetGame() {
    const r = await API.post('/api/reset', {});
    if (r.ok) {
        applyState(r.state);
        showToast('已重置', 'success');
    }
}

async function passMove() {
    if (State.isThinking || State.gameOver) return;
    await makePass(State.nextColor);
}

async function aiMove() {
    if (State.isThinking || State.gameOver) return;
    await aiMoveOnce();
}

async function resign() {
    if (State.gameOver) {
        showToast('对局已结束', 'info');
        return;
    }
    if (!confirm('确定认输吗？')) return;
    const r = await API.post('/api/resign', { color: State.humanColor });
    if (r.ok) {
        applyState(r.state);
    }
}

async function saveSgf() {
    const r = await API.post('/api/save-sgf');
    if (r.ok) {
        showToast('已保存: ' + r.filename, 'success');
    } else {
        showToast('保存失败: ' + (r.error || ''), 'error');
    }
}

async function startTrain() {
    if (State.training) {
        showToast('训练已在进行中', 'info');
        return;
    }
    const n = parseInt($('trainBatchSize').value) || 10;
    const r = await API.post('/api/train/auto', { n, save_every: 10, delay: 0.0 });
    if (r.ok) {
        showToast(r.message, 'success');
        State.training = true;
        if (State.pollTimer) clearInterval(State.pollTimer);
        State.pollTimer = setInterval(refreshStats, 1500);
    } else {
        showToast(r.error || '启动失败', 'error');
    }
}

async function stopTrain() {
    await API.post('/api/train/stop');
    showToast('已请求停止训练', 'success');
    State.training = false;
    if (State.pollTimer) {
        clearInterval(State.pollTimer);
        State.pollTimer = null;
    }
    refreshStats();
}

async function trainOneStep() {
    if (State.isThinking) return;
    setThinking(true);
    const r = await API.post('/api/train/step', {});
    setThinking(false);
    if (r.ok) {
        showToast(`第${r.result.game_no}局: ${
            r.result.winner === BLACK ? '黑胜' :
            r.result.winner === WHITE ? '白胜' : '和棋'
        }`, 'success');
        await refreshStats();
        await refreshHistory();
    }
}

function changeMode(mode) {
    State.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
    });
    if (mode === 'ai_ai') {
        // AI连续对弈：每0.6s 走一步
        if (State.autoPlayTimer) clearInterval(State.autoPlayTimer);
        State.autoPlayTimer = setInterval(async () => {
            if (State.gameOver) {
                clearInterval(State.autoPlayTimer);
                State.autoPlayTimer = null;
                return;
            }
            await aiMoveOnce();
        }, 600);
        showToast('AI连续对弈已启动', 'success');
    } else {
        if (State.autoPlayTimer) {
            clearInterval(State.autoPlayTimer);
            State.autoPlayTimer = null;
        }
    }
    if (mode === 'ai_selfplay') {
        startTrain();
    }
}

// ========== 事件绑定 ==========
function setupEvents() {
    // 模式按钮
    document.querySelectorAll('.mode-btn').forEach(b => {
        b.addEventListener('click', () => changeMode(b.dataset.mode));
    });
    // 控制按钮
    $('btnNewGame').addEventListener('click', newGame);
    $('btnReset').addEventListener('click', resetGame);
    $('btnPass').addEventListener('click', passMove);
    $('btnAiMove').addEventListener('click', aiMove);
    $('btnResign').addEventListener('click', resign);
    $('btnSaveSgf').addEventListener('click', saveSgf);
    $('btnAnalyze').addEventListener('click', requestAnalysis);
    $('btnTrainStart').addEventListener('click', startTrain);
    $('btnTrainStop').addEventListener('click', stopTrain);
    $('btnTrainStep').addEventListener('click', trainOneStep);
    // 模态框
    $('modalCloseBtn').addEventListener('click', () => {
        $('gameOverModal').classList.remove('active');
    });
    $('gameOverModal').addEventListener('click', (e) => {
        if (e.target.id === 'gameOverModal') {
            $('gameOverModal').classList.remove('active');
        }
    });
    // 热键
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
        if (e.code === 'Space') {
            e.preventDefault();
            aiMove();
        } else if (e.key === 'p' || e.key === 'P') {
            passMove();
        } else if (e.key === 'r' || e.key === 'R') {
            resetGame();
        } else if (e.key === 'n' || e.key === 'N') {
            newGame();
        } else if (e.key === 'a' || e.key === 'A') {
            requestAnalysis();
        }
    });
    // 窗口大小变化
    window.addEventListener('resize', () => {
        drawBoard();
    });
}

// ========== 启动 ==========
async function init() {
    setupEvents();
    setupBoardClick();
    // 加载初始状态
    const s = await API.get('/api/state');
    applyState(s);
    await refreshStats();
    await refreshHistory();
    drawBoard();
    // 训练中则开始轮询
    if (s.is_training || (State.training)) {
        if (State.pollTimer) clearInterval(State.pollTimer);
        State.pollTimer = setInterval(refreshStats, 1500);
    }
}

window.addEventListener('load', init);
