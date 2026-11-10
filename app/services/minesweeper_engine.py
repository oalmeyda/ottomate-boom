"""Core Minesweeper game engine for Ottomate Boom.

Implements classic Beginner, Intermediate, and Expert board geometries,
safe first-click opening relocation, BFS cascade reveals, chord clicking,
3BV benchmark evaluation, and deterministic daily challenge seed generation.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import random
import re
from typing import Any, Literal

from ottomate_core.grid_engine import get_grid_neighbors as _core_get_neighbors

MIN_GAME_DATE = "2026-10-01"

DIFFICULTY_CONFIGS: dict[str, dict[str, int]] = {
    "beginner": {"rows": 9, "cols": 9, "mines": 10},
    "intermediate": {"rows": 16, "cols": 16, "mines": 40},
    "expert": {"rows": 16, "cols": 30, "mines": 99},
}


def validate_date_str(date_str: str | None) -> str:
    """Validate or fallback to current UTC date in YYYY-MM-DD format (bounded between 2026-10-01 and today)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not date_str:
        return today
    date_str = date_str.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return today
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        if date_str < MIN_GAME_DATE:
            return MIN_GAME_DATE
        if date_str > today:
            return today
        return date_str
    except ValueError:
        return today


def get_daily_seed(date_str: str, difficulty: str) -> str:
    """Derive deterministic seed for a daily challenge date and difficulty."""
    valid_date = validate_date_str(date_str)
    diff = difficulty.lower().strip()
    if diff not in DIFFICULTY_CONFIGS:
        diff = "beginner"
    raw = f"ottomate_boom_{valid_date}_{diff}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_neighbors(row: int, col: int, rows: int, cols: int) -> list[tuple[int, int]]:
    """Return valid 8-directional neighbor coordinates for (row, col)."""
    return _core_get_neighbors(row, col, rows, cols, include_diagonals=True)


def compute_3bv(rows: int, cols: int, mines: set[tuple[int, int]]) -> int:
    """Compute Bechtel's Board Benchmark Value (3BV).

    The minimum number of non-flag clicks required to clear the board:
    1. Count of connected components of 0-value (empty) cells.
    2. Plus each non-mine cell with >0 adjacent mines that is NOT adjacent
       to any 0-value cell.
    """
    total_cells = rows * cols
    if not mines or len(mines) >= total_cells:
        return 0

    # Calculate neighbor mine counts
    counts: dict[tuple[int, int], int] = {}
    for r in range(rows):
        for c in range(cols):
            if (r, c) in mines:
                continue
            c_mines = sum(1 for nr, nc in get_neighbors(r, c, rows, cols) if (nr, nc) in mines)
            counts[(r, c)] = c_mines

    # 1. Connected components of 0-cells
    zero_cells = {pos for pos, cnt in counts.items() if cnt == 0}
    visited_zeros: set[tuple[int, int]] = set()
    openings = 0

    for zr, zc in zero_cells:
        if (zr, zc) in visited_zeros:
            continue
        openings += 1
        queue = deque([(zr, zc)])
        visited_zeros.add((zr, zc))
        while queue:
            curr_r, curr_c = queue.popleft()
            for nr, nc in get_neighbors(curr_r, curr_c, rows, cols):
                if (nr, nc) in zero_cells and (nr, nc) not in visited_zeros:
                    visited_zeros.add((nr, nc))
                    queue.append((nr, nc))

    # 2. Cells that do NOT touch any 0-cell
    isolated_numbered_cells = 0
    for (r, c), cnt in counts.items():
        if cnt > 0:
            touches_zero = any((nr, nc) in zero_cells for nr, nc in get_neighbors(r, c, rows, cols))
            if not touches_zero:
                isolated_numbered_cells += 1

    return openings + isolated_numbered_cells


class MinesweeperBoard:
    """Server-side authoritative Minesweeper board simulation."""

    def __init__(
        self,
        difficulty: str = "beginner",
        seed: str | None = None,
        is_daily: bool = False,
        date_str: str | None = None,
    ) -> None:
        self.difficulty = difficulty.lower().strip()
        if self.difficulty not in DIFFICULTY_CONFIGS:
            self.difficulty = "beginner"

        cfg = DIFFICULTY_CONFIGS[self.difficulty]
        self.rows = cfg["rows"]
        self.cols = cfg["cols"]
        self.mine_count = cfg["mines"]
        self.is_daily = is_daily
        self.date_str = validate_date_str(date_str) if is_daily else None

        self.seed = seed or (
            get_daily_seed(self.date_str, self.difficulty)
            if is_daily and self.date_str
            else hashlib.sha256(f"{random.random()}:{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        )

        self.mines: set[tuple[int, int]] = set()
        self.counts: list[list[int]] = [[0] * self.cols for _ in range(self.rows)]
        self.revealed: set[tuple[int, int]] = set()
        self.flagged: set[tuple[int, int]] = set()
        self.question_marks: set[tuple[int, int]] = set()
        self.status: Literal["not_started", "in_progress", "won", "lost"] = "not_started"
        self.first_click: tuple[int, int] | None = None
        self.exploded_at: tuple[int, int] | None = None
        self.elapsed_seconds: int = 0
        self.clicks: int = 0
        self.three_bv: int = 0

        self._place_initial_mines()

    def _place_initial_mines(self) -> None:
        """Place mines deterministically according to the seed."""
        rng = random.Random(self.seed)
        all_coords = [(r, c) for r in range(self.rows) for c in range(self.cols)]
        self.mines = set(rng.sample(all_coords, self.mine_count))
        self._recompute_counts()
        self.three_bv = compute_3bv(self.rows, self.cols, self.mines)

    def _recompute_counts(self) -> None:
        """Recalculate adjacent mine counts for each cell."""
        self.counts = [[0] * self.cols for _ in range(self.rows)]
        for r in range(self.rows):
            for c in range(self.cols):
                if (r, c) in self.mines:
                    self.counts[r][c] = -1
                else:
                    self.counts[r][c] = sum(
                        1 for nr, nc in get_neighbors(r, c, self.rows, self.cols) if (nr, nc) in self.mines
                    )

    def _relocate_mines_for_safe_first_click(self, first_r: int, first_c: int) -> None:
        """Ensure first_click cell and its 8 neighbors contain 0 mines.

        Relocates conflicting mines to the earliest available non-mine cells
        outside the 3x3 forbidden zone in a deterministic scan.
        """
        forbidden = set(get_neighbors(first_r, first_c, self.rows, self.cols)) | {(first_r, first_c)}
        conflicts = [m for m in self.mines if m in forbidden]

        if not conflicts:
            return

        # Scan row by row for destination cells not in mines and not in forbidden
        dest_candidates = []
        for r in range(self.rows):
            for c in range(self.cols):
                pos = (r, c)
                if pos not in self.mines and pos not in forbidden:
                    dest_candidates.append(pos)

        dest_idx = 0
        for mine in conflicts:
            self.mines.remove(mine)
            if dest_idx < len(dest_candidates):
                self.mines.add(dest_candidates[dest_idx])
                dest_idx += 1
            else:
                # Fallback: any non-mine cell
                for r in range(self.rows):
                    for c in range(self.cols):
                        if (r, c) not in self.mines and (r, c) != (first_r, first_c):
                            self.mines.add((r, c))
                            break

        self._recompute_counts()
        self.three_bv = compute_3bv(self.rows, self.cols, self.mines)

    def reveal(self, row: int, col: int) -> dict[str, Any]:
        """Reveal cell at (row, col). Returns action result."""
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return {"success": False, "error": "Invalid coordinates"}

        if self.status in ("won", "lost"):
            return {"success": False, "error": "Game already concluded"}

        if (row, col) in self.flagged:
            return {"success": False, "error": "Cannot reveal flagged cell"}

        self.clicks += 1

        # Safe opening on move 1
        if self.status == "not_started":
            self.status = "in_progress"
            self.first_click = (row, col)
            self._relocate_mines_for_safe_first_click(row, col)

        # Hit a mine
        if (row, col) in self.mines:
            self.status = "lost"
            self.exploded_at = (row, col)
            return {
                "success": True,
                "status": "lost",
                "exploded_at": [row, col],
                "revealed_count": len(self.revealed),
            }

        # Safe reveal with BFS flood fill for 0-cells
        if (row, col) not in self.revealed:
            queue = deque([(row, col)])
            self.revealed.add((row, col))
            while queue:
                curr_r, curr_c = queue.popleft()
                if self.counts[curr_r][curr_c] == 0:
                    for nr, nc in get_neighbors(curr_r, curr_c, self.rows, self.cols):
                        if (nr, nc) not in self.revealed and (nr, nc) not in self.flagged:
                            self.revealed.add((nr, nc))
                            if self.counts[nr][nc] == 0:
                                queue.append((nr, nc))

        # Check win condition
        total_safe_cells = (self.rows * self.cols) - self.mine_count
        if len(self.revealed) >= total_safe_cells:
            self.status = "won"
            # Auto-flag remaining mines
            self.flagged = set(self.mines)

        return {
            "success": True,
            "status": self.status,
            "revealed_count": len(self.revealed),
            "is_won": self.status == "won",
        }

    def toggle_flag(self, row: int, col: int) -> dict[str, Any]:
        """Toggle flag on cell at (row, col)."""
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return {"success": False, "error": "Invalid coordinates"}

        if self.status in ("won", "lost"):
            return {"success": False, "error": "Game already concluded"}

        if (row, col) in self.revealed:
            return {"success": False, "error": "Cannot flag revealed cell"}

        if (row, col) in self.flagged:
            self.flagged.remove((row, col))
            state = "hidden"
        else:
            self.flagged.add((row, col))
            state = "flagged"

        return {
            "success": True,
            "row": row,
            "col": col,
            "state": state,
            "flags_placed": len(self.flagged),
            "flags_remaining": self.mine_count - len(self.flagged),
        }

    def chord(self, row: int, col: int) -> dict[str, Any]:
        """Perform chord action on revealed numbered cell."""
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return {"success": False, "error": "Invalid coordinates"}

        if self.status != "in_progress":
            return {"success": False, "error": "Cannot chord now"}

        if (row, col) not in self.revealed or self.counts[row][col] <= 0:
            return {"success": False, "error": "Can only chord on revealed numbered cells"}

        neighbors = get_neighbors(row, col, self.rows, self.cols)
        flagged_neighbors = [n for n in neighbors if n in self.flagged]

        # Chord condition: flagged neighbors must equal cell number
        if len(flagged_neighbors) != self.counts[row][col]:
            return {
                "success": False,
                "error": "Flagged neighbors count does not match cell number",
            }

        self.clicks += 1
        unrevealed_unflagged = [
            n for n in neighbors if n not in self.revealed and n not in self.flagged
        ]

        # Check if chord revealed any mine (misplaced flag)
        detonated_mine = next((n for n in unrevealed_unflagged if n in self.mines), None)
        if detonated_mine:
            self.status = "lost"
            self.exploded_at = detonated_mine
            return {
                "success": True,
                "status": "lost",
                "exploded_at": list(detonated_mine),
            }

        # Reveal all safe neighbors (using BFS for any 0s)
        for nr, nc in unrevealed_unflagged:
            if (nr, nc) not in self.revealed:
                queue = deque([(nr, nc)])
                self.revealed.add((nr, nc))
                while queue:
                    curr_r, curr_c = queue.popleft()
                    if self.counts[curr_r][curr_c] == 0:
                        for nn_r, nn_c in get_neighbors(curr_r, curr_c, self.rows, self.cols):
                            if (nn_r, nn_c) not in self.revealed and (nn_r, nn_c) not in self.flagged:
                                self.revealed.add((nn_r, nn_c))
                                if self.counts[nn_r][nn_c] == 0:
                                    queue.append((nn_r, nn_c))

        total_safe_cells = (self.rows * self.cols) - self.mine_count
        if len(self.revealed) >= total_safe_cells:
            self.status = "won"
            self.flagged = set(self.mines)

        return {
            "success": True,
            "status": self.status,
            "revealed_count": len(self.revealed),
            "is_won": self.status == "won",
        }

    def to_client_state(self, is_admin: bool = False) -> dict[str, Any]:
        """Serialize board state for client consumption, masking unrevealed mines unless game over."""
        is_over = self.status in ("won", "lost")
        grid = []

        for r in range(self.rows):
            row_data = []
            for c in range(self.cols):
                pos = (r, c)
                is_mine = pos in self.mines
                is_flagged = pos in self.flagged
                is_revealed = pos in self.revealed

                cell: dict[str, Any] = {
                    "r": r,
                    "c": c,
                    "revealed": is_revealed,
                    "flagged": is_flagged,
                }

                if is_revealed:
                    cell["value"] = self.counts[r][c]
                elif is_over:
                    # Reveal all mines and wrong flags on game over
                    if is_mine:
                        cell["is_mine"] = True
                        if pos == self.exploded_at:
                            cell["exploded"] = True
                    elif is_flagged and not is_mine:
                        cell["wrong_flag"] = True
                elif is_admin:
                    cell["is_mine"] = is_mine

                row_data.append(cell)
            grid.append(row_data)

        return {
            "difficulty": self.difficulty,
            "rows": self.rows,
            "cols": self.cols,
            "mine_count": self.mine_count,
            "flags_placed": len(self.flagged),
            "flags_remaining": self.mine_count - len(self.flagged),
            "revealed_count": len(self.revealed),
            "status": self.status,
            "is_daily": self.is_daily,
            "date": self.date_str,
            "seed": self.seed,
            "three_bv": self.three_bv,
            "clicks": self.clicks,
            "elapsed_seconds": self.elapsed_seconds,
            "grid": grid,
        }
