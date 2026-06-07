/* XW-GO 围棋自对弈训练AI - 主前端脚本（改进版） */
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
    nextColor: 1,
    mode: 'human_ai',
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
    t.textContent = msg.replace(/[！!]+$/g, '');
    t.className = 'toast show ' + type;
    t.setAttribute('role', type === 'error' ? 'alert' : 'status');
    setTimeout(() => {
        t.className = 'toast ' + type;
    }, 3000);
}

function coordToStr(x, y) {
    if (x === -1 && y === -1) return '虚着';
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
    canvas.setAttribute('aria-label', `围棋棋盘 ${size}×${size}，当前手数${State.moveCount}，${State.nextColor === BLACK ? '轮到黑方' : '轮到白方'}`);

    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    State.margin = 30;
    State.cellSize = (W - 2 * State.margin) / (size - 1);
    State.stoneRadius = State.cellSize * 0.42;

    const grad = ctx.createLinearGradient(0, 0, W * 0.3, H * 0.7);
    grad.addColorStop(0, '#D2A050');
    grad.addColorStop(0.5, '#C89848');
    grad.addColorStop(1, '#A87838');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    ctx.save();
    ctx.globalAlpha = 0.05;
    ctx.strokeStyle = '#3E2723';
    ctx.lineWidth = 0.5;
    for (let i = 0; i < 20; i++) {
        ctx.beginPath();
        const y = Math.random() * H;
        ctx.moveTo(0, y);
        ctx.bezierCurveTo(W * 0.3, y + (Math.random() - 0.5) * 16,
                          W * 0.7, y + (Math.random() - 0.5) * 16,
                          W, y + (Math.random() - 0.5) * 8);
        ctx.stroke();
    }
    ctx.restore();

    ctx.strokeStyle = '#2E1A0E';
    ctx.lineWidth = 2.5;
    ctx.strokeRect(State.margin - 7, State.margin - 7,
                   State.cellSize * (size - 1) + 14, State.cellSize * (size - 1) + 14);

    ctx.strokeStyle = '#2E1A0E';
    ctx.lineWidth = 0.9;
    ctx.beginPath();
    for (let i = 0; i < size; i++) {
        const p = State.margin + i * State.cellSize;
        ctx.moveTo(State.margin, p);
        ctx.lineTo(State.margin + (size - 1) * State.cellSize, p);
        ctx.moveTo(p, State.margin);
        ctx.lineTo(p, State.margin + (size - 1) * State.cellSize);
    }
    ctx.stroke();

    drawStarPoints(ctx, size);

    ctx.fillStyle = '#2E1A0E';
    ctx.font = `600 ${Math.max(10, State.cellSize * 0.23)}px "Geist Sans", "Microsoft YaHei", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < size; i++) {
        const p = State.margin + i * State.cellSize;
        let col = String.fromCharCode(65 + i);
        if (col >= 'I') col = String.fromCharCode(col.charCodeAt(0) + 1);
        ctx.fillText(col, p, State.margin - 15);
        ctx.fillText(col, p, State.margin + (size - 1) * State.cellSize + 15);
        const rowLabel = String(size - i);
        ctx.fillText(rowLabel, State.margin - 15, p);
        ctx.fillText(rowLabel, State.margin + (size - 1) * State.cellSize + 15, p);
    }

    for (let x = 0; x < size; x++) {
        for (let y = 0; y < size; y++) {
            const c = State.board[x] && State.board[x][y];
            if (c !== EMPTY) {
                drawStone(ctx, x, y, c,
                    State.lastMove && State.lastMove[0] === x && State.lastMove[1] === y);
            }
        }
    }

    if (State.koPoint) {
        const [kx, ky] = State.koPoint;
        const px = State.margin + ky * State.cellSize;
        const py = State.margin + kx * State.cellSize;
        ctx.strokeStyle = 'rgba(192, 57, 43, 0.7)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.arc(px, py, State.stoneRadius * 0.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
    }
}

function drawStarPoints(ctx, size) {
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
    ctx.fillStyle = '#2E1A0E';
    const r = Math.max(3, State.cellSize * 0.09);
    for (const [x, y] of stars) {
        const px = State.margin + y * State.cellSize;
        const py = State.margin + x * State.cellSize;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();
    }
}

function drawStone(ctx, x, y, color, isLast) {
    const px = State.margin + y * State.cellSize;
    const py = State.margin + x * State.cellSize;
    const r = State.stoneRadius;

    ctx.save();
    ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
    ctx.shadowBlur = 5;
    ctx.shadowOffsetX = 1;
    ctx.shadowOffsetY = 2;

    if (color === BLACK) {
        const grad = ctx.createRadialGradient(
            px - r * 0.28, py - r * 0.28, r * 0.08,
            px, py, r);
        grad.addColorStop(0, '#3a3a3a');
        grad.addColorStop(0.55, '#111');
        grad.addColorStop(1, '#050505');
        ctx.fillStyle = grad;
    } else {
        const grad = ctx.createRadialGradient(
            px - r * 0.28, py - r * 0.28, r * 0.08,
            px, py, r);
        grad.addColorStop(0, '#f5f0e8');
        grad.addColorStop(0.65, '#e8e0d0');
        grad.addColorStop(1, '#c0b8a8');
        ctx.fillStyle = grad;
        ctx.strokeStyle = '#a09880';
        ctx.lineWidth = 0.5;
    }
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fill();
    if (color === WHITE) {
        ctx.stroke();
    }
    ctx.restore();

    if (isLast) {
        ctx.strokeStyle = color === BLACK ? 'rgba(232, 168, 32, 0.75)' : 'rgba(192, 57, 43, 0.6)';
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.arc(px, py, r * 0.38, 0, Math.PI * 2);
        ctx.stroke();
    }
}

// ========== 点击落子 ==========
function setupBoardClick() {
    const canvas = $('board');
    canvas.addEventListener('click', async (e) => {
        if (State.isThinking) return;
        if (State.gameOver) return;
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

    canvas.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const cx = rect.width / 2;
            const cy = rect.height / 2;
            const x = Math.round((cy - State.margin) / State.cellSize);
            const y = Math.round((cx - State.margin) / State.cellSize);
            if (x >= 0 && x < State.size && y >= 0 && y < State.size) {
                await makeMove(x, y, State.nextColor);
            }
        }
    });
}

async function makeMove(x, y, color) {
    setThinking(true);
    try {
        const r = await API.post('/api/move', { x, y, color });
        if (!r.ok) {
            showToast(r.error || '无法落子于此处', 'error');
            return false;
        }
        applyState(r.state);
        return true;
    } catch (e) {
        showToast('网络错误：' + e.message, 'error');
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
            showToast(r.error || 'AI 无法走子', 'error');
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

    $('moveCount').textContent = State.moveCount;
    $('passCount').textContent = State.passCount;
    $('boardSize').textContent = `${State.size}×${State.size}`;

    const turn = $('turnIndicator');
    if (State.gameOver) {
        turn.innerHTML = '<span class="stone-icon black" aria-hidden="true"></span>已终局';
    } else {
        if (State.nextColor === BLACK) {
            turn.innerHTML = '<span class="stone-icon black" aria-hidden="true"></span>黑方走子';
        } else {
            turn.innerHTML = '<span class="stone-icon white" aria-hidden="true"></span>白方走子';
        }
    }

    drawBoard();
    updateMoveList();

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
        list.parentElement.scrollTop = list.parentElement.scrollHeight;
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
    const modal = $('gameOverModal');
    modal.classList.add('active');
    modal.querySelector('.modal-close').focus();
}

// ========== 训练统计 ==========
async function refreshStats() {
    const r = await API.get('/api/stats');
    if (!r || (!r.ok && r.total_games === undefined)) return;
    $('statTotalGames').textContent = r.total_games || 0;
    $('statPhase').textContent = r.phase === 'random' ? '随机阶段' : '学习阶段';
    $('statQStates').textContent = r.q_states || 0;
    $('statVisits').textContent = r.total_visits || 0;
    const bw = ((r.winrate_black_last10 || 0) * 100).toFixed(1) + '%';
    const ww = ((r.winrate_white_last10 || 0) * 100).toFixed(1) + '%';
    $('statBlackWinrate').textContent = bw;
    $('statWhiteWinrate').textContent = ww;
    State.training = r.is_training || false;
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
                    borderColor: '#E8A820',
                    backgroundColor: 'rgba(232, 168, 32, 0.12)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                },
                {
                    label: '白胜率(滑动20局)',
                    data: (data.winrate_black_smoothed || []).map(v => 1 - v),
                    borderColor: '#3A8FD4',
                    backgroundColor: 'rgba(58, 143, 212, 0.08)',
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
                    labels: { color: '#b8b0a0', font: { size: 10, family: "'Geist Sans', sans-serif" } }
                },
                tooltip: {
                    backgroundColor: 'rgba(10, 8, 5, 0.9)',
                    titleColor: '#E8A820',
                    bodyColor: '#f0ece4',
                    borderColor: 'rgba(232, 168, 32, 0.2)',
                    borderWidth: 1,
                }
            },
            scales: {
                x: {
                    ticks: { color: '#6a6560', font: { size: 9 }, maxTicksLimit: 8 },
                    grid: { color: 'rgba(255,255,255,0.04)' }
                },
                y: {
                    min: 0, max: 1,
                    ticks: { color: '#6a6560', font: { size: 9 } },
                    grid: { color: 'rgba(255,255,255,0.04)' }
                }
            }
        }
    });
}

// ========== 棋局分析 ==========
async function requestAnalysis() {
    const r = await API.post('/api/analyze');
    if (!r.ok) {
        showToast('分析请求失败', 'error');
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
        lines.push(`<div class="analysis-line value" style="color:#E8A820">${winnerStr}（差 ${s.margin}子）</div>`);
        lines.push(`<div class="analysis-line">${s.reason}</div>`);
    } else {
        lines.push('<div class="analysis-line warn">对局未结束</div>');
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
    const overlay = $('boardOverlay');
    const indicator = $('thinkingIndicator');
    overlay.classList.toggle('active', on);
    indicator.setAttribute('aria-label', on ? 'AI 正在思考中' : '');
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
    if (!confirm('确认认输吗')) return;
    const r = await API.post('/api/resign', { color: State.humanColor });
    if (r.ok) {
        applyState(r.state);
    }
}

async function saveSgf() {
    const r = await API.post('/api/save-sgf');
    if (r.ok) {
        showToast('已保存：' + r.filename, 'success');
    } else {
        showToast('保存失败：' + (r.error || '未知错误'), 'error');
    }
}

async function startTrain() {
    if (State.training) {
        showToast('训练正在进行中', 'info');
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

async function refreshHardware() {
    try {
        const info = await API.get('/api/hardware');
        const be = $('hwBackend');
        be.textContent = info.backend_detail || info.backend;
        be.className = 'hw-val backend-' + info.backend;
        $('hwCpu').textContent = `${info.cpu}（${info.cores}核）`;
        const gpuList = $('hwGpuList');
        gpuList.innerHTML = '';
        if (info.gpus && info.gpus.length) {
            const title = document.createElement('div');
            title.className = 'hw-key';
            title.style.marginTop = '8px';
            title.textContent = `GPU（${info.gpus.length}）`;
            gpuList.appendChild(title);
            for (const g of info.gpus) {
                const d = document.createElement('div');
                d.className = 'hw-device';
                const tl = (g.type || '').toLowerCase();
                if (tl.includes('cann') || tl.includes('ascend')) d.classList.add('cann');
                else if (tl.includes('cuda')) d.classList.add('cuda');
                else if (tl.includes('dml') || tl.includes('directml')) d.classList.add('dml');
                const mem = g.memory_gb ? ` · ${g.memory_gb}GB` : '';
                const dev = g.device ? ` · ${g.device}` : '';
                d.innerHTML = `<div class="hw-device-name">${g.type}: ${g.name}</div>
                    <div class="hw-device-meta">${(g.vendor || '')}${mem}${dev}</div>`;
                gpuList.appendChild(d);
            }
        }
        const npuList = $('hwNpuList');
        npuList.innerHTML = '';
        if (info.npus && info.npus.length) {
            const title = document.createElement('div');
            title.className = 'hw-key';
            title.style.marginTop = '8px';
            title.textContent = `NPU（${info.npus.length}）`;
            npuList.appendChild(title);
            for (const n of info.npus) {
                const d = document.createElement('div');
                d.className = 'hw-device cann';
                d.innerHTML = `<div class="hw-device-name">${n.type}: ${n.name}</div>
                    <div class="hw-device-meta">vendor: ${n.vendor || '—'} · framework: ${n.framework || '—'}</div>`;
                npuList.appendChild(d);
            }
        }
        const threads = $('hwThreads');
        if (info.thread_env) {
            const t = info.thread_env;
            threads.textContent = `线程：OMP=${t.OMP_NUM_THREADS || '-'} MKL=${t.MKL_NUM_THREADS || '-'} OpenBLAS=${t.OPENBLAS_NUM_THREADS || '-'}`;
        }
    } catch (e) {
        $('hwBackend').textContent = '检测失败：' + e.message;
    }
}

async function refreshHardwareForce() {
    const r = await API.post('/api/hardware/refresh');
    if (r.ok) {
        showToast('硬件检测已更新', 'success');
        await refreshHardware();
    }
}

async function trainOneStep() {
    if (State.isThinking) return;
    setThinking(true);
    const r = await API.post('/api/train/step', {});
    setThinking(false);
    if (r.ok) {
        const resultText = r.result.winner === BLACK ? '黑胜' :
                          r.result.winner === WHITE ? '白胜' : '和棋';
        showToast(`第${r.result.game_no}局：${resultText}`, 'success');
        await refreshStats();
        await refreshHistory();
    }
}

function changeMode(mode) {
    State.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => {
        const isActive = b.dataset.mode === mode;
        b.classList.toggle('active', isActive);
        b.setAttribute('aria-checked', isActive);
    });
    if (mode === 'ai_ai') {
        if (State.autoPlayTimer) clearInterval(State.autoPlayTimer);
        State.autoPlayTimer = setInterval(async () => {
            if (State.gameOver) {
                clearInterval(State.autoPlayTimer);
                State.autoPlayTimer = null;
                return;
            }
            await aiMoveOnce();
        }, 600);
        showToast('AI 连续对弈已启动', 'success');
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
    document.querySelectorAll('.mode-btn').forEach(b => {
        b.addEventListener('click', () => changeMode(b.dataset.mode));
    });

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
    if ($('btnHwRefresh')) $('btnHwRefresh').addEventListener('click', refreshHardwareForce);

    $('modalCloseBtn').addEventListener('click', () => {
        $('gameOverModal').classList.remove('active');
    });
    $('gameOverModal').addEventListener('click', (e) => {
        if (e.target.id === 'gameOverModal') {
            $('gameOverModal').classList.remove('active');
        }
    });

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

    window.addEventListener('resize', () => {
        drawBoard();
    });

    const skipLink = document.querySelector('.skip-link');
    if (skipLink) {
        skipLink.addEventListener('click', (e) => {
            e.preventDefault();
            const target = document.querySelector(skipLink.getAttribute('href'));
            if (target) {
                target.focus();
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    }
}

// ========== 启动 ==========
async function init() {
    setupEvents();
    setupBoardClick();
    const s = await API.get('/api/state');
    applyState(s);
    await refreshStats();
    await refreshHistory();
    await refreshHardware();
    drawBoard();
    if (s.is_training || State.training) {
        if (State.pollTimer) clearInterval(State.pollTimer);
        State.pollTimer = setInterval(refreshStats, 1500);
    }
}

window.addEventListener('load', init);
