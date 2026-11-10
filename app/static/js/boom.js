/**
 * Ottomate Boom - Classic Minesweeper Web Client
 *
 * Implements classic Minesweeper mechanics with Beginner, Intermediate, and Expert
 * geometries, deterministic daily challenges, retro LED HUD & face states,
 * chord clicking, Web Audio SFX, and global leaderboards.
 */

// Global State
let currentUser = null;
let currentMode = "daily"; // "daily" | "casual"
let currentDifficulty = "beginner"; // "beginner" | "intermediate" | "expert"
let currentDate = new Date().toISOString().split("T")[0];
let flagMode = false; // Mobile touch toggle

const DIFFICULTY_SPECS = {
  beginner: { rows: 9, cols: 9, mines: 10, label: "Beginner (9x9)" },
  intermediate: { rows: 16, cols: 16, mines: 40, label: "Intermediate (16x16)" },
  expert: { rows: 16, cols: 30, mines: 99, label: "Expert (30x16)" },
};

let gameState = {
  gameId: null,
  seed: null,
  rows: 9,
  cols: 9,
  mineCount: 10,
  grid: [], // 2D array: { r, c, isMine: bool, revealed: bool, flagged: bool, value: int, exploded: bool, wrongFlag: bool }
  mines: new Set(),
  revealedCount: 0,
  flagsPlaced: 0,
  status: "not_started", // "not_started" | "in_progress" | "won" | "lost"
  firstClick: null,
  elapsedSeconds: 0,
  timerInterval: null,
  clicks: 0,
  threeBv: 0,
};

// Web Audio API Sound Synthesizer (delegates to shared ottomate-audio.js)
function playClickSound() {
  if (window.Ottomate?.audio?.playClick) {
    window.Ottomate.audio.playClick();
  }
}

function playFlagSound() {
  if (window.Ottomate?.audio?.playFlag) {
    window.Ottomate.audio.playFlag();
  }
}

function playBoomSound() {
  if (window.Ottomate?.audio?.playExplosion) {
    window.Ottomate.audio.playExplosion();
  }
}

function playWinSound() {
  if (window.Ottomate?.audio?.playWinFanfare) {
    window.Ottomate.audio.playWinFanfare();
  }
}

// Pseudo-Random Number Generator (seeded)
function Mulberry32(seedStr) {
  let h = 0;
  for (let i = 0; i < seedStr.length; i++) {
    h = Math.imul(31, h) + seedStr.charCodeAt(i) | 0;
  }
  return function() {
    h |= 0; h = h + 0x6D2B79F5 | 0;
    let t = Math.imul(h ^ h >>> 15, 1 | h);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

// Helper: 8 Neighbors
function getNeighbors(r, c, rows, cols) {
  const list = [];
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      const nr = r + dr;
      const nc = c + dc;
      if (nr >= 0 && nr < rows && nc >= 0 && nc < cols) {
        list.push([nr, nc]);
      }
    }
  }
  return list;
}

// Initialize Board Data Structure
function setupLocalBoard(difficulty, mode, dateStr) {
  stopTimer();
  const spec = DIFFICULTY_SPECS[difficulty] || DIFFICULTY_SPECS.beginner;
  const rows = spec.rows;
  const cols = spec.cols;
  const mineCount = spec.mines;

  const seed = (mode === "daily")
    ? `ottomate_boom_${dateStr}_${difficulty}`
    : `casual_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;

  const grid = [];
  for (let r = 0; r < rows; r++) {
    const row = [];
    for (let c = 0; c < cols; c++) {
      row.push({
        r,
        c,
        isMine: false,
        revealed: false,
        flagged: false,
        value: 0,
        exploded: false,
        wrongFlag: false,
      });
    }
    grid.push(row);
  }

  // Pre-seed initial mines deterministically
  const rng = Mulberry32(seed);
  const allCoords = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      allCoords.push([r, c]);
    }
  }
  // Shuffle coords
  for (let i = allCoords.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [allCoords[i], allCoords[j]] = [allCoords[j], allCoords[i]];
  }

  const mines = new Set();
  for (let i = 0; i < mineCount; i++) {
    const [mr, mc] = allCoords[i];
    mines.add(`${mr},${mc}`);
    grid[mr][mc].isMine = true;
  }

  // Compute values
  recomputeValues(grid, rows, cols, mines);

  gameState = {
    gameId: `boom_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
    seed,
    rows,
    cols,
    mineCount,
    grid,
    mines,
    revealedCount: 0,
    flagsPlaced: 0,
    status: "not_started",
    firstClick: null,
    elapsedSeconds: 0,
    timerInterval: null,
    clicks: 0,
    threeBv: 0,
  };

  updateHUD();
  setFaceState("idle");
  renderGrid();
  hideWinBanner();
}

function recomputeValues(grid, rows, cols, mines) {
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (mines.has(`${r},${c}`)) {
        grid[r][c].isMine = true;
        grid[r][c].value = -1;
      } else {
        grid[r][c].isMine = false;
        const neighbors = getNeighbors(r, c, rows, cols);
        grid[r][c].value = neighbors.filter(([nr, nc]) => mines.has(`${nr},${nc}`)).length;
      }
    }
  }
}

// Safe First-Click Relocation
function ensureSafeFirstClick(firstR, firstC) {
  const forbidden = new Set(getNeighbors(firstR, firstC, gameState.rows, gameState.cols).map(([r, c]) => `${r},${c}`));
  forbidden.add(`${firstR},${firstC}`);

  const conflicts = [];
  for (const mKey of gameState.mines) {
    if (forbidden.has(mKey)) {
      conflicts.push(mKey);
    }
  }

  if (conflicts.length === 0) return;

  // Find candidate replacement cells row by row
  const candidates = [];
  for (let r = 0; r < gameState.rows; r++) {
    for (let c = 0; c < gameState.cols; c++) {
      const k = `${r},${c}`;
      if (!gameState.mines.has(k) && !forbidden.has(k)) {
        candidates.push(k);
      }
    }
  }

  let candIdx = 0;
  for (const cMine of conflicts) {
    gameState.mines.delete(cMine);
    const [mr, mc] = cMine.split(",").map(Number);
    gameState.grid[mr][mc].isMine = false;

    if (candIdx < candidates.length) {
      const repKey = candidates[candIdx++];
      gameState.mines.add(repKey);
      const [rr, rc] = repKey.split(",").map(Number);
      gameState.grid[rr][rc].isMine = true;
    }
  }

  recomputeValues(gameState.grid, gameState.rows, gameState.cols, gameState.mines);
}

// Timer Functions
function startTimer() {
  if (gameState.timerInterval) return;
  gameState.timerInterval = setInterval(() => {
    gameState.elapsedSeconds++;
    updateHUD();
    if (gameState.elapsedSeconds >= 999) {
      stopTimer();
    }
  }, 1000);
}

function stopTimer() {
  if (gameState.timerInterval) {
    clearInterval(gameState.timerInterval);
    gameState.timerInterval = null;
  }
}

// Face State (idle, press, dead, cool)
function setFaceState(state) {
  const faceBtn = document.getElementById("face-button");
  if (!faceBtn) return;
  if (state === "press") {
    faceBtn.textContent = "😮";
  } else if (state === "dead") {
    faceBtn.textContent = "😵";
  } else if (state === "cool") {
    faceBtn.textContent = "😎";
  } else {
    faceBtn.textContent = "🙂";
  }
}

// HUD Updates
function updateHUD() {
  const minesDisplay = document.getElementById("display-mines");
  const timerDisplay = document.getElementById("display-timer");

  const remMines = gameState.mineCount - gameState.flagsPlaced;
  if (minesDisplay) {
    const formattedMines = Math.max(-99, Math.min(999, remMines));
    minesDisplay.textContent = String(formattedMines).padStart(3, "0");
  }

  if (timerDisplay) {
    const formattedTimer = Math.min(999, gameState.elapsedSeconds);
    timerDisplay.textContent = String(formattedTimer).padStart(3, "0");
  }
}

// Render Grid DOM
function renderGrid() {
  const container = document.getElementById("minesweeper-grid");
  if (!container) return;

  container.innerHTML = "";
  container.style.gridTemplateColumns = `repeat(${gameState.cols}, var(--boom-cell-size))`;
  container.style.gridTemplateRows = `repeat(${gameState.rows}, var(--boom-cell-size))`;

  for (let r = 0; r < gameState.rows; r++) {
    for (let c = 0; c < gameState.cols; c++) {
      const cellData = gameState.grid[r][c];
      const cellEl = document.createElement("div");
      cellEl.className = "boom-cell";
      cellEl.id = `cell-${r}-${c}`;
      cellEl.dataset.r = r;
      cellEl.dataset.c = c;

      updateCellDOM(cellEl, cellData);

      // Event Listeners
      cellEl.addEventListener("mousedown", (e) => handleCellMouseDown(e, r, c));
      cellEl.addEventListener("mouseup", (e) => handleCellMouseUp(e, r, c));
      cellEl.addEventListener("contextmenu", (e) => handleCellContextMenu(e, r, c));
      cellEl.addEventListener("touchstart", (e) => handleCellTouchStart(e, r, c), { passive: true });
      cellEl.addEventListener("touchend", (e) => handleCellTouchEnd(e, r, c));

      container.appendChild(cellEl);
    }
  }
}

function updateCellDOM(cellEl, cellData) {
  cellEl.className = "boom-cell";
  cellEl.textContent = "";
  delete cellEl.dataset.num;

  if (cellData.revealed) {
    cellEl.classList.add("cell-revealed");
    if (cellData.isMine) {
      cellEl.classList.add("cell-mine");
      cellEl.textContent = "💣";
      if (cellData.exploded) {
        cellEl.classList.add("cell-exploded");
      }
    } else if (cellData.value > 0) {
      cellEl.dataset.num = cellData.value;
      cellEl.textContent = cellData.value;
    }
  } else {
    cellEl.classList.add("cell-covered");
    if (cellData.flagged) {
      cellEl.classList.add("cell-flagged");
      cellEl.textContent = "🚩";
    }
    // Game over reveal
    if (gameState.status === "lost") {
      if (cellData.isMine && !cellData.flagged) {
        cellEl.classList.add("cell-mine");
        cellEl.textContent = "💣";
      } else if (cellData.flagged && !cellData.isMine) {
        cellEl.classList.add("cell-wrong-flag");
        cellEl.textContent = "❌";
      }
    }
  }
}

// Cell Interaction Handlers
let isMouseDown = false;
let touchTimer = null;

function handleCellMouseDown(e, r, c) {
  if (gameState.status === "won" || gameState.status === "lost") return;
  if (e.button === 0) { // Left click
    isMouseDown = true;
    setFaceState("press");
  }
}

function handleCellMouseUp(e, r, c) {
  if (!isMouseDown && e.button === 0) return;
  isMouseDown = false;
  if (gameState.status === "won" || gameState.status === "lost") return;

  setFaceState("idle");

  if (e.button === 0) {
    if (flagMode) {
      toggleFlag(r, c);
    } else {
      revealCell(r, c);
    }
  } else if (e.button === 1) { // Middle click -> chord
    chordCell(r, c);
  }
}

function handleCellContextMenu(e, r, c) {
  e.preventDefault();
  if (gameState.status === "won" || gameState.status === "lost") return;
  toggleFlag(r, c);
}

function handleCellTouchStart(e, r, c) {
  if (gameState.status === "won" || gameState.status === "lost") return;
  touchTimer = setTimeout(() => {
    // Long-press triggers flag
    toggleFlag(r, c);
    touchTimer = null;
  }, 350);
}

function handleCellTouchEnd(e, r, c) {
  if (touchTimer) {
    clearTimeout(touchTimer);
    touchTimer = null;
    if (flagMode) {
      toggleFlag(r, c);
    } else {
      revealCell(r, c);
    }
  }
}

// Toggle Flag Action
function toggleFlag(r, c) {
  const cell = gameState.grid[r][c];
  if (cell.revealed) {
    // Tapping a revealed numbered cell can trigger chord!
    if (cell.value > 0) {
      chordCell(r, c);
    }
    return;
  }

  cell.flagged = !cell.flagged;
  gameState.flagsPlaced += cell.flagged ? 1 : -1;
  playFlagSound();

  const cellEl = document.getElementById(`cell-${r}-${c}`);
  if (cellEl) updateCellDOM(cellEl, cell);

  updateHUD();
}

// Reveal Cell Action
function revealCell(r, c) {
  const cell = gameState.grid[r][c];
  if (cell.flagged) return;

  if (cell.revealed) {
    // Clicking an already revealed number triggers chord!
    if (cell.value > 0) {
      chordCell(r, c);
    }
    return;
  }

  // Safe opening on move 1
  if (gameState.status === "not_started") {
    gameState.status = "in_progress";
    gameState.firstClick = [r, c];
    ensureSafeFirstClick(r, c);
    startTimer();
  }

  gameState.clicks++;

  // Detonation (Mine)
  if (cell.isMine) {
    detonateGame(r, c);
    return;
  }

  playClickSound();

  // BFS Flood Fill for 0-cells
  const queue = [[r, c]];
  cell.revealed = true;
  gameState.revealedCount++;

  while (queue.length > 0) {
    const [currR, currC] = queue.shift();
    const currCell = gameState.grid[currR][currC];

    if (currCell.value === 0) {
      const neighbors = getNeighbors(currR, currC, gameState.rows, gameState.cols);
      for (const [nr, nc] of neighbors) {
        const nCell = gameState.grid[nr][nc];
        if (!nCell.revealed && !nCell.flagged && !nCell.isMine) {
          nCell.revealed = true;
          gameState.revealedCount++;
          if (nCell.value === 0) {
            queue.push([nr, nc]);
          }
        }
      }
    }
  }

  // Refresh visible grid
  refreshAllCells();

  // Check Win Condition
  const totalSafeCells = (gameState.rows * gameState.cols) - gameState.mineCount;
  if (gameState.revealedCount >= totalSafeCells) {
    winGame();
  }
}

// Chord Action (reveal adjacent unflagged cells when flags == number)
function chordCell(r, c) {
  const cell = gameState.grid[r][c];
  if (!cell.revealed || cell.value <= 0) return;

  const neighbors = getNeighbors(r, c, gameState.rows, gameState.cols);
  const flaggedNeighbors = neighbors.filter(([nr, nc]) => gameState.grid[nr][nc].flagged);

  if (flaggedNeighbors.length !== cell.value) {
    return;
  }

  gameState.clicks++;
  const unrevealedUnflagged = neighbors.filter(([nr, nc]) => {
    const ncCell = gameState.grid[nr][nc];
    return !ncCell.revealed && !ncCell.flagged;
  });

  // Check if any chorded cell is a mine (incorrect flag placed)
  const hitMine = unrevealedUnflagged.find(([nr, nc]) => gameState.grid[nr][nc].isMine);
  if (hitMine) {
    detonateGame(hitMine[0], hitMine[1]);
    return;
  }

  playClickSound();

  // Reveal all safe neighbors
  for (const [nr, nc] of unrevealedUnflagged) {
    const nCell = gameState.grid[nr][nc];
    if (!nCell.revealed) {
      nCell.revealed = true;
      gameState.revealedCount++;
      if (nCell.value === 0) {
        // Expand 0 cascade
        const queue = [[nr, nc]];
        while (queue.length > 0) {
          const [qr, qc] = queue.shift();
          const qCell = gameState.grid[qr][qc];
          if (qCell.value === 0) {
            for (const [nnR, nnC] of getNeighbors(qr, qc, gameState.rows, gameState.cols)) {
              const target = gameState.grid[nnR][nnC];
              if (!target.revealed && !target.flagged && !target.isMine) {
                target.revealed = true;
                gameState.revealedCount++;
                if (target.value === 0) queue.push([nnR, nnC]);
              }
            }
          }
        }
      }
    }
  }

  refreshAllCells();

  const totalSafeCells = (gameState.rows * gameState.cols) - gameState.mineCount;
  if (gameState.revealedCount >= totalSafeCells) {
    winGame();
  }
}

function refreshAllCells() {
  for (let r = 0; r < gameState.rows; r++) {
    for (let c = 0; c < gameState.cols; c++) {
      const cellEl = document.getElementById(`cell-${r}-${c}`);
      if (cellEl) updateCellDOM(cellEl, gameState.grid[r][c]);
    }
  }
}

// Detonation (Game Lost)
function detonateGame(r, c) {
  stopTimer();
  gameState.status = "lost";
  setFaceState("dead");
  playBoomSound();

  gameState.grid[r][c].exploded = true;
  gameState.grid[r][c].revealed = true;

  refreshAllCells();
  submitFinishResult("lost");
}

// Victory (Game Won)
function winGame() {
  stopTimer();
  gameState.status = "won";
  setFaceState("cool");
  playWinSound();

  // Auto flag all mines
  for (const mKey of gameState.mines) {
    const [mr, mc] = mKey.split(",").map(Number);
    gameState.grid[mr][mc].flagged = true;
  }
  gameState.flagsPlaced = gameState.mineCount;
  updateHUD();
  refreshAllCells();

  showWinBanner();
  submitFinishResult("won");
}

function showWinBanner() {
  const banner = document.getElementById("win-banner");
  if (!banner) return;
  const timeStr = `${gameState.elapsedSeconds}s`;
  document.getElementById("win-time-val").textContent = timeStr;
  document.getElementById("win-clicks-val").textContent = gameState.clicks;
  banner.style.display = "flex";
}

function hideWinBanner() {
  const banner = document.getElementById("win-banner");
  if (banner) banner.style.display = "none";
}

// Submit Result to Server
async function submitFinishResult(status) {
  if (!currentUser) return;

  try {
    const payload = {
      game_id: gameState.gameId,
      difficulty: currentDifficulty,
      mode: currentMode,
      date: (currentMode === "daily") ? currentDate : null,
      seed: gameState.seed,
      status: status,
      elapsed_seconds: gameState.elapsedSeconds,
      clicks: gameState.clicks,
      cells_revealed: gameState.revealedCount,
      flags_placed: gameState.flagsPlaced,
      three_bv: gameState.threeBv,
      first_click: gameState.firstClick,
    };

    const res = await apiFetch("/api/game/finish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      if (currentMode === "daily") {
        fetchDailyStatus();
      }
    }
  } catch (err) {
    console.error("Failed submitting game result:", err);
  }
}

// Difficulty & Mode Selectors
function switchDifficulty(diff) {
  if (!DIFFICULTY_SPECS[diff]) return;
  currentDifficulty = diff;

  document.querySelectorAll(".diff-btn").forEach((btn) => {
    btn.classList.remove("active", "active-diff-beginner", "active-diff-intermediate", "active-diff-expert");
    if (btn.dataset.diff === diff) {
      btn.classList.add("active", `active-diff-${diff}`);
    }
  });

  setupLocalBoard(currentDifficulty, currentMode, currentDate);
}

function switchMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });

  const dateCluster = document.getElementById("date-navigator-cluster");
  if (dateCluster) {
    dateCluster.style.display = (mode === "daily") ? "inline-flex" : "none";
  }

  setupLocalBoard(currentDifficulty, currentMode, currentDate);
  if (mode === "daily") {
    fetchDailyStatus();
  }
}

function changeDateByDays(delta) {
  const d = new Date(currentDate);
  d.setDate(d.getDate() + delta);
  const nextDate = d.toISOString().split("T")[0];
  const today = new Date().toISOString().split("T")[0];

  if (nextDate < "2026-10-01" || nextDate > today) return;
  currentDate = nextDate;

  const dateText = document.getElementById("date-display-text");
  if (dateText) dateText.textContent = currentDate;

  setupLocalBoard(currentDifficulty, currentMode, currentDate);
  fetchDailyStatus();
}

function toggleFlagMode() {
  flagMode = !flagMode;
  const btn = document.getElementById("btn-flag-toggle");
  if (btn) {
    btn.classList.toggle("active", flagMode);
    btn.textContent = flagMode ? "🚩 Flagging" : "⛏️ Digging";
  }
}

// Daily Status Check
async function fetchDailyStatus() {
  if (!currentUser) return;
  try {
    const res = await apiFetch(`/api/daily/status?date=${currentDate}`);
    if (res.ok) {
      const data = await res.json();
      updateDailyStatusBadges(data);
    }
  } catch (err) {
    console.warn("Could not fetch daily status:", err);
  }
}

function updateDailyStatusBadges(statusData) {
  const bBadge = document.getElementById("status-badge-beginner");
  const iBadge = document.getElementById("status-badge-intermediate");
  const eBadge = document.getElementById("status-badge-expert");

  if (bBadge) bBadge.textContent = (statusData.beginner_status === "won") ? "✅" : (statusData.beginner_status === "lost" ? "❌" : "");
  if (iBadge) iBadge.textContent = (statusData.intermediate_status === "won") ? "✅" : (statusData.intermediate_status === "lost" ? "❌" : "");
  if (eBadge) eBadge.textContent = (statusData.expert_status === "won") ? "✅" : (statusData.expert_status === "lost" ? "❌" : "");
}

// Leaderboard Modal
let currentLbScope = "daily";
let currentLbDiff = "all";

function openLeaderboardModal() {
  const modal = document.getElementById("leaderboard-modal");
  if (modal) {
    modal.style.display = "flex";
    fetchLeaderboardData();
  }
}

function closeLeaderboardModal() {
  const modal = document.getElementById("leaderboard-modal");
  if (modal) modal.style.display = "none";
}

function switchLbScope(scope) {
  currentLbScope = scope;
  document.querySelectorAll(".lb-scope-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.scope === scope);
  });
  fetchLeaderboardData();
}

function switchLbDiff(diff) {
  currentLbDiff = diff;
  document.querySelectorAll(".lb-diff-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.diff === diff);
  });
  fetchLeaderboardData();
}

async function fetchLeaderboardData() {
  const tbody = document.getElementById("leaderboard-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 1.5rem;">Loading leaderboard...</td></tr>`;

  try {
    let url = `/api/leaderboard?scope=${currentLbScope}&difficulty=${currentLbDiff}`;
    if (currentLbScope === "daily") {
      url += `&date=${currentDate}`;
    }
    const res = await apiFetch(url);
    if (!res.ok) throw new Error("Failed fetching leaderboard");
    const data = await res.json();

    if (!data.leaderboard || data.leaderboard.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 1.5rem;">No games recorded yet for this filter.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    data.leaderboard.forEach((entry) => {
      const isMe = currentUser && (entry.user_email.toLowerCase() === currentUser.email.toLowerCase());
      const tr = document.createElement("tr");
      if (isMe) tr.className = "highlight-me";

      const rankBadge = (entry.rank === 1) ? "🥇 1" : (entry.rank === 2) ? "🥈 2" : (entry.rank === 3) ? "🥉 3" : entry.rank;
      const timeStr = entry.best_time_seconds != null ? `${entry.best_time_seconds}s` : "--";

      tr.innerHTML = `
        <td style="font-weight: 700;">${rankBadge}</td>
        <td>
          <span style="font-weight: 600; color: #f8fafc;">${escapeHtml(entry.display_name)}</span>
          ${isMe ? '<span style="font-size: 0.72rem; background: #3b82f6; color: white; padding: 1px 5px; border-radius: 4px; margin-left: 4px;">YOU</span>' : ''}
        </td>
        <td><span style="text-transform: capitalize; font-size: 0.82rem; color: #cbd5e1;">${entry.difficulty}</span></td>
        <td style="font-weight: 700; color: #38bdf8;">${timeStr}</td>
        <td>${entry.games_won} / ${entry.games_played} (${entry.win_rate}%)</td>
        <td>🔥 ${entry.current_streak} (Max ${entry.max_streak})</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #ef4444; padding: 1.5rem;">Failed loading leaderboard.</td></tr>`;
  }
}

// Stats Modal
function openStatsModal() {
  const modal = document.getElementById("stats-modal");
  if (modal) {
    modal.style.display = "flex";
    fetchUserStatsData();
  }
}

function closeStatsModal() {
  const modal = document.getElementById("stats-modal");
  if (modal) modal.style.display = "none";
}

async function fetchUserStatsData() {
  const container = document.getElementById("user-stats-container");
  if (!container) return;
  container.innerHTML = `<div style="text-align: center; padding: 1.5rem; color: #94a3b8;">Loading career statistics...</div>`;

  try {
    const res = await apiFetch("/api/stats");
    if (!res.ok) throw new Error("Failed fetching stats");
    const s = await res.json();

    container.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">${s.games_played}</div>
          <div class="stat-label">Played</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color: #4ade80;">${s.games_won}</div>
          <div class="stat-label">Won</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${s.win_rate}%</div>
          <div class="stat-label">Win Rate</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color: #f59e0b;">🔥 ${s.current_streak}</div>
          <div class="stat-label">Streak (Max ${s.max_streak})</div>
        </div>
      </div>

      <h4 style="margin: 1.25rem 0 0.5rem 0; color: #cbd5e1; font-size: 0.95rem;">🏆 Personal Best Times</h4>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value" style="color: #10b981;">${s.beginner.best_time_seconds ? s.beginner.best_time_seconds + 's' : '--'}</div>
          <div class="stat-label">Beginner (9x9)</div>
          <small style="color: #64748b; font-size: 0.72rem;">${s.beginner.won} wins</small>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color: #3b82f6;">${s.intermediate.best_time_seconds ? s.intermediate.best_time_seconds + 's' : '--'}</div>
          <div class="stat-label">Intermediate (16x16)</div>
          <small style="color: #64748b; font-size: 0.72rem;">${s.intermediate.won} wins</small>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color: #ef4444;">${s.expert.best_time_seconds ? s.expert.best_time_seconds + 's' : '--'}</div>
          <div class="stat-label">Expert (30x16)</div>
          <small style="color: #64748b; font-size: 0.72rem;">${s.expert.won} wins</small>
        </div>
      </div>

      <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 0.75rem 1rem; margin-top: 1rem; display: flex; align-items: center; justify-content: space-between;">
        <span style="color: #94a3b8; font-size: 0.88rem;">📅 Daily Challenges Solved:</span>
        <strong style="color: #f8fafc; font-size: 1.1rem;">${s.daily_challenges_completed}</strong>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div style="text-align: center; padding: 1.5rem; color: #ef4444;">Failed loading stats.</div>`;
  }
}

// History Modal
function openHistoryModal() {
  const modal = document.getElementById("history-modal");
  if (modal) {
    modal.style.display = "flex";
    fetchHistoryData();
  }
}

function closeHistoryModal() {
  const modal = document.getElementById("history-modal");
  if (modal) modal.style.display = "none";
}

async function fetchHistoryData() {
  const tbody = document.getElementById("history-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 1.5rem;">Loading history...</td></tr>`;

  try {
    const res = await apiFetch("/api/history?limit=30");
    if (!res.ok) throw new Error("Failed fetching history");
    const items = await res.json();

    if (!items || items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 1.5rem;">No recent games found.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    items.forEach((item) => {
      const tr = document.createElement("tr");
      const isWon = item.status === "won";
      const statusBadge = isWon ? `<span style="color: #4ade80; font-weight: 700;">WIN</span>` : `<span style="color: #ef4444;">BOOM</span>`;
      const dateStr = item.date || (item.completed_at ? item.completed_at.substring(0, 10) : "--");

      tr.innerHTML = `
        <td style="color: #94a3b8;">${dateStr}</td>
        <td style="text-transform: capitalize;">${item.mode}</td>
        <td style="text-transform: capitalize;">${item.difficulty}</td>
        <td>${statusBadge}</td>
        <td style="font-weight: 600; color: #38bdf8;">${item.elapsed_seconds}s</td>
        <td>${item.clicks} clicks</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #ef4444; padding: 1.5rem;">Failed loading history.</td></tr>`;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- API Fetch Helper ---
async function apiFetch(path, options = {}) {
  if (window.Ottomate && typeof window.Ottomate.api === "function") {
    try {
      const data = await window.Ottomate.api(path, options);
      return { ok: true, status: 200, json: async () => data };
    } catch (err) {
      if (err.status === 401) onUserSignedOut();
      return {
        ok: false,
        status: err.status || 500,
        json: async () => ({ detail: err.message }),
      };
    }
  }
  const headers = options.headers ? { ...options.headers } : {};
  const token =
    (typeof window.Ottomate?.getStoredAuthToken === "function"
      ? window.Ottomate.getStoredAuthToken()
      : null) ||
    localStorage.getItem("ottomate_auth_token") ||
    localStorage.getItem("auth_token") ||
    "";
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const opts = { ...options, headers };
  const res = await fetch(path, opts);
  if (res.status === 401) {
    if (window.Ottomate && typeof window.Ottomate.clearAuthToken === "function") {
      window.Ottomate.clearAuthToken();
    }
    onUserSignedOut();
  }
  return res;
}

// Authentication & Core Wiring
async function initAuth() {
  if (window.Ottomate) {
    try {
      if (window.Ottomate.people && typeof window.Ottomate.people.init === "function") {
        window.Ottomate.people.init({
          appName: "Ottomate Boom",
          onError: (msg) => console.warn(msg),
        });
      }

      await window.Ottomate.initHeader({
        onSignOut: () => logout(),
        onBrandClicked: () => setupLocalBoard(currentDifficulty, currentMode, currentDate),
        onProfileClicked: () => showProfileModal(),
        onDirectoryClicked: () => showDirectoryModal(),
      });
    } catch (err) {
      console.warn("Ottomate header/people init error:", err);
    }
  }

  let config = null;
  try {
    const cfgRes = await fetch("/api/config");
    if (cfgRes.ok) {
      config = await cfgRes.json();
    }
  } catch (err) {
    console.warn("Failed loading /api/config:", err);
  }

  if (config && window.Ottomate && typeof window.Ottomate.setupSignIn === "function") {
    window.Ottomate.setupSignIn(config, async (token) => {
      if (token && typeof window.Ottomate.storeAuthToken === "function") {
        window.Ottomate.storeAuthToken(token);
      }
      await restoreSession();
    });

    // Also render Google Sign-In button on the hero guest card
    if (config.google_client_id && typeof window.Ottomate.renderGoogleSignIn === "function") {
      window.Ottomate.renderGoogleSignIn({
        clientId: config.google_client_id,
        rootId: "g-signin-root-guest",
        width: 280,
        size: "large",
        onCredential: async (token) => {
          if (token && typeof window.Ottomate.storeAuthToken === "function") {
            window.Ottomate.storeAuthToken(token);
          }
          await restoreSession();
        },
      });
    }

    if (config.dev_mode) {
      const devGuest = document.getElementById("dev-signin-root-guest");
      const devGuestBtn = document.getElementById("btn-dev-login-guest");
      if (devGuest) devGuest.style.display = "block";
      if (devGuestBtn) {
        devGuestBtn.style.display = "inline-block";
        devGuestBtn.onclick = async () => {
          if (typeof window.Ottomate.storeAuthToken === "function") {
            window.Ottomate.storeAuthToken("dev-token", "dev");
          }
          await restoreSession();
        };
      }
    }
  }

  await restoreSession();
}

async function restoreSession() {
  const token =
    (typeof window.Ottomate?.getStoredAuthToken === "function"
      ? window.Ottomate.getStoredAuthToken()
      : null) ||
    localStorage.getItem("ottomate_auth_token") ||
    localStorage.getItem("auth_token");

  if (!token) {
    onUserSignedOut();
    return;
  }

  try {
    const meRes = await apiFetch("/api/me");
    if (meRes.ok) {
      currentUser = await meRes.json();
      onUserSignedIn(currentUser);
    } else {
      onUserSignedOut();
    }
  } catch (err) {
    console.warn("Failed checking session:", err);
    onUserSignedOut();
  }
}

function onUserSignedIn(user) {
  currentUser = user;
  const guestCard = document.getElementById("guest-card");
  const gameView = document.getElementById("game-view");
  const btnDir = document.getElementById("btn-directory");

  if (guestCard) guestCard.style.display = "none";
  if (gameView) {
    gameView.style.display = "flex";
    gameView.style.flexDirection = "column";
    gameView.style.alignItems = "center";
  }

  if (window.Ottomate) {
    if (typeof window.Ottomate.updateProfilePill === "function") {
      window.Ottomate.updateProfilePill(user);
    }
    if (typeof window.Ottomate.toggleAuthButtons === "function") {
      window.Ottomate.toggleAuthButtons(true);
    }
  }

  if (btnDir && (user.system_role === "super_admin" || user.roles?.boom === "game_admin")) {
    btnDir.style.display = "inline-block";
  }

  fetchDailyStatus();
}

function onUserSignedOut() {
  currentUser = null;
  const guestCard = document.getElementById("guest-card");
  const gameView = document.getElementById("game-view");
  const btnDir = document.getElementById("btn-directory");

  if (guestCard) guestCard.style.display = "block";
  if (gameView) gameView.style.display = "none";
  if (btnDir) btnDir.style.display = "none";

  if (window.Ottomate && typeof window.Ottomate.toggleAuthButtons === "function") {
    window.Ottomate.toggleAuthButtons(false);
  }
}

function showProfileModal() {
  if (window.Ottomate && window.Ottomate.people && typeof window.Ottomate.people.showProfileModal === "function") {
    window.Ottomate.people.showProfileModal();
  }
}

function showDirectoryModal() {
  if (window.Ottomate && window.Ottomate.people && typeof window.Ottomate.people.showDirectoryModal === "function") {
    window.Ottomate.people.showDirectoryModal();
  }
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch (_) {}
  if (window.Ottomate && typeof window.Ottomate.clearAuthToken === "function") {
    window.Ottomate.clearAuthToken();
  }
  onUserSignedOut();
  window.location.reload();
}

// Initialization on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  const dateDisplay = document.getElementById("date-display-text");
  if (dateDisplay) dateDisplay.textContent = currentDate;

  initAuth();
  setupLocalBoard(currentDifficulty, currentMode, currentDate);
});
