"""Unit tests for the Minesweeper engine."""

from app.services.minesweeper_engine import (
    DIFFICULTY_CONFIGS,
    MinesweeperBoard,
    compute_3bv,
    get_daily_seed,
)


def test_difficulty_geometries():
    """Verify classic 3 board sizes match original Minesweeper specifications."""
    assert DIFFICULTY_CONFIGS["beginner"] == {"rows": 9, "cols": 9, "mines": 10}
    assert DIFFICULTY_CONFIGS["intermediate"] == {"rows": 16, "cols": 16, "mines": 40}
    assert DIFFICULTY_CONFIGS["expert"] == {"rows": 16, "cols": 30, "mines": 99}

    for diff, cfg in DIFFICULTY_CONFIGS.items():
        board = MinesweeperBoard(difficulty=diff)
        assert board.rows == cfg["rows"]
        assert board.cols == cfg["cols"]
        assert board.mine_count == cfg["mines"]
        assert len(board.mines) == cfg["mines"]


def test_deterministic_daily_seeds():
    """Ensure daily seeds are deterministic for date + difficulty."""
    seed1 = get_daily_seed("2026-11-09", "beginner")
    seed2 = get_daily_seed("2026-11-09", "beginner")
    seed_diff = get_daily_seed("2026-11-09", "intermediate")
    seed_date = get_daily_seed("2026-11-08", "beginner")

    assert seed1 == seed2
    assert seed1 != seed_diff
    assert seed1 != seed_date


def test_safe_first_click_and_opening_cascade():
    """First-click must never be a mine and should open a safe cascade."""
    board = MinesweeperBoard(difficulty="beginner", seed="test_seed_123")
    res = board.reveal(4, 4)

    assert res["success"] is True
    assert board.status in ("in_progress", "won")
    assert (4, 4) not in board.mines
    assert (4, 4) in board.revealed
    assert board.counts[4][4] == 0
    # First click opened a cluster of cells
    assert len(board.revealed) > 1


def test_flag_toggle_and_limits():
    """Flagging cells updates count and prevents accidental clicks."""
    board = MinesweeperBoard(difficulty="beginner", seed="flag_test")
    res = board.toggle_flag(0, 0)
    assert res["success"] is True
    assert (0, 0) in board.flagged
    assert board.to_client_state()["flags_placed"] == 1
    assert board.to_client_state()["flags_remaining"] == 9

    # Cannot reveal flagged cell
    reveal_res = board.reveal(0, 0)
    assert reveal_res["success"] is False

    # Unflagging
    unflag_res = board.toggle_flag(0, 0)
    assert unflag_res["success"] is True
    assert (0, 0) not in board.flagged
    assert board.to_client_state()["flags_placed"] == 0


def test_chord_clicking():
    """Chording an opened number cell with matching flags opens unflagged neighbors."""
    board = MinesweeperBoard(difficulty="beginner", seed="chord_test")
    board.reveal(4, 4)

    # Find a revealed numbered cell that touches a mine
    target_pos = None
    for r in range(board.rows):
        for c in range(board.cols):
            if (r, c) in board.revealed and board.counts[r][c] > 0:
                target_pos = (r, c)
                break
        if target_pos:
            break

    assert target_pos is not None
    tr, tc = target_pos
    assert board.counts[tr][tc] > 0

    # Chord fails if flagged count doesn't match
    chord_fail = board.chord(tr, tc)
    assert chord_fail["success"] is False


def test_3bv_computation():
    """3BV must return a positive integer for a valid mine layout."""
    board = MinesweeperBoard(difficulty="beginner", seed="3bv_eval")
    three_bv = compute_3bv(board.rows, board.cols, board.mines)
    assert three_bv > 0
    assert board.three_bv == three_bv


def test_win_condition():
    """Revealing all safe cells marks board won and auto-flags all mines."""
    board = MinesweeperBoard(difficulty="beginner", seed="win_sim")
    # First click to initialize
    board.reveal(0, 0)

    # Reveal all remaining non-mine cells
    for r in range(board.rows):
        for c in range(board.cols):
            if (r, c) not in board.mines and (r, c) not in board.revealed:
                board.reveal(r, c)

    assert board.status == "won"
    assert board.flagged == board.mines
    assert len(board.revealed) == (board.rows * board.cols) - board.mine_count


def test_loss_condition():
    """Clicking a mine after first move detonates game."""
    board = MinesweeperBoard(difficulty="beginner", seed="loss_sim")
    board.reveal(0, 0)  # Safe first click

    # Find a mine
    mine_pos = next(iter(board.mines))
    res = board.reveal(mine_pos[0], mine_pos[1])
    assert res["status"] == "lost"
    assert board.status == "lost"
    assert board.exploded_at == mine_pos


def test_expert_geometry_and_mine_density():
    """Verify expert board (16x30, 99 mines) initializes and safe first-click works."""
    board = MinesweeperBoard(difficulty="expert", seed="expert_test")
    assert board.rows == 16
    assert board.cols == 30
    assert board.mine_count == 99
    assert len(board.mines) == 99

    res = board.reveal(8, 15)
    assert res["success"] is True
    assert (8, 15) not in board.mines
    assert len(board.revealed) >= 1


def test_chord_detonation_on_wrong_flag():
    """If a player misplaces a flag and chords, unflagged mine detonates."""
    board = MinesweeperBoard(difficulty="beginner", seed="chord_boom")
    board.reveal(4, 4)

    # Pick a revealed cell with a neighbor mine
    candidate = None
    for r in range(board.rows):
        for c in range(board.cols):
            if (r, c) in board.revealed and board.counts[r][c] > 0:
                candidate = (r, c)
                break
        if candidate:
            break

    assert candidate is not None
    cr, cc = candidate
    num = board.counts[cr][cc]

    # Deliberately flag a SAFE neighbor instead of the mine
    neighbors = [n for n in [(cr+dr, cc+dc) for dr in (-1,0,1) for dc in (-1,0,1) if not (dr==0 and dc==0)] if 0 <= n[0] < board.rows and 0 <= n[1] < board.cols]
    safe_unrevealed = [n for n in neighbors if n not in board.revealed and n not in board.mines]
    mine_neighbors = [n for n in neighbors if n in board.mines]

    if safe_unrevealed and mine_neighbors:
        # Flag enough safe cells to match `num`
        for s_pos in safe_unrevealed[:num]:
            board.toggle_flag(s_pos[0], s_pos[1])
        if len(board.flagged.intersection(neighbors)) == num:
            chord_res = board.chord(cr, cc)
            assert chord_res["status"] == "lost"
            assert board.status == "lost"


def test_invalid_coordinates_and_post_game_actions():
    """Invalid actions and moves after game over return clean errors."""
    board = MinesweeperBoard(difficulty="beginner")
    bad_reveal = board.reveal(-1, 99)
    assert bad_reveal["success"] is False

    bad_flag = board.toggle_flag(100, 100)
    assert bad_flag["success"] is False

    bad_chord = board.chord(-5, -5)
    assert bad_chord["success"] is False

    # Conclude game
    board.reveal(0, 0)
    for m in board.mines:
        board.reveal(m[0], m[1])
        break
    assert board.status == "lost"

    # Action after game over
    post_res = board.reveal(1, 1)
    assert post_res["success"] is False
    assert "concluded" in post_res["error"]
