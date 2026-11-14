"""API integration tests for Ottomate Boom."""

from __future__ import annotations

from fastapi.testclient import TestClient
from ottomate_core.auth import User, get_current_user
import pytest

from app.main import app


def _make_client_for_user(
    email: str = "player@example.com", name: str = "Player One"
) -> TestClient:
    user = User(
        email=email,
        display_name=name,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


def test_start_new_game(isolated_fake_db):
    """Test creating a new Minesweeper game session."""
    client = _make_client_for_user("alice@example.com", "Alice")
    res = client.post(
        "/api/game/new",
        json={"difficulty": "beginner", "mode": "daily", "date": "2026-11-09"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["rows"] == 9
    assert data["cols"] == 9
    assert data["mine_count"] == 10
    assert data["status"] == "not_started"
    assert data["is_daily"] is True
    assert "game_id" in data
    assert len(data["grid"]) == 9
    assert len(data["grid"][0]) == 9


def test_game_action_reveal_and_flag(isolated_fake_db):
    """Test live reveal and flag actions."""
    client = _make_client_for_user("bob@example.com", "Bob")
    new_res = client.post(
        "/api/game/new",
        json={"difficulty": "beginner", "mode": "casual"},
    )
    assert new_res.status_code == 200
    game_id = new_res.json()["game_id"]

    # Flag cell (0, 0)
    flag_res = client.post(
        "/api/game/action",
        json={"game_id": game_id, "action": "flag", "row": 0, "col": 0},
    )
    assert flag_res.status_code == 200
    assert flag_res.json()["flags_placed"] == 1

    # Safe reveal (4, 4)
    reveal_res = client.post(
        "/api/game/action",
        json={"game_id": game_id, "action": "reveal", "row": 4, "col": 4},
    )
    assert reveal_res.status_code == 200
    assert reveal_res.json()["status"] in ("in_progress", "won")
    assert reveal_res.json()["revealed_count"] > 0


def test_game_finish_and_stats_aggregation(isolated_fake_db):
    """Test recording a finished game and querying stats and leaderboards."""
    client = _make_client_for_user("charlie@example.com", "Charlie")

    # Record a won daily game
    finish_res = client.post(
        "/api/game/finish",
        json={
            "game_id": "test_win_game_1",
            "difficulty": "beginner",
            "mode": "daily",
            "date": "2026-11-09",
            "seed": "seed_123",
            "status": "won",
            "elapsed_seconds": 42,
            "clicks": 18,
            "cells_revealed": 71,
            "flags_placed": 10,
            "three_bv": 15,
            "first_click": [4, 4],
        },
    )
    assert finish_res.status_code == 200
    assert finish_res.json()["status"] == "won"

    # Query daily status
    daily_res = client.get("/api/daily/status?date=2026-11-09")
    assert daily_res.status_code == 200
    d_data = daily_res.json()
    assert d_data["beginner_status"] == "won"
    assert d_data["is_daily_completed"] is True

    # Query leaderboard
    lb_res = client.get("/api/leaderboard?scope=daily&date=2026-11-09&difficulty=beginner")
    assert lb_res.status_code == 200
    lb_data = lb_res.json()
    assert len(lb_data["leaderboard"]) >= 1
    assert lb_data["leaderboard"][0]["user_email"] == "charlie@example.com"
    assert lb_data["leaderboard"][0]["best_time_seconds"] == 42
    assert lb_data["my_stats"]["rank"] == 1

    # Query personal stats
    stats_res = client.get("/api/stats")
    assert stats_res.status_code == 200
    s_data = stats_res.json()
    assert s_data["games_played"] == 1
    assert s_data["games_won"] == 1
    assert s_data["win_rate"] == 100.0
    assert s_data["current_streak"] == 1
    assert s_data["beginner"]["best_time_seconds"] == 42

    # Query history
    hist_res = client.get("/api/history")
    assert hist_res.status_code == 200
    h_data = hist_res.json()
    assert len(h_data) == 1
    assert h_data[0]["game_id"] == "test_win_game_1"
    assert h_data[0]["status"] == "won"
    assert h_data[0]["elapsed_seconds"] == 42


def test_leaderboard_multi_player_ranking(isolated_fake_db):
    """Test multi-player leaderboard ranking by win time."""
    p1 = _make_client_for_user("fast@example.com", "Fast Player")
    p1.post(
        "/api/game/finish",
        json={
            "game_id": "fast_win",
            "difficulty": "intermediate",
            "mode": "daily",
            "date": "2026-11-09",
            "status": "won",
            "elapsed_seconds": 35,
            "clicks": 30,
            "cells_revealed": 216,
        },
    )

    p2 = _make_client_for_user("slow@example.com", "Slow Player")
    p2.post(
        "/api/game/finish",
        json={
            "game_id": "slow_win",
            "difficulty": "intermediate",
            "mode": "daily",
            "date": "2026-11-09",
            "status": "won",
            "elapsed_seconds": 95,
            "clicks": 60,
            "cells_revealed": 216,
        },
    )

    lb_res = p1.get("/api/leaderboard?scope=daily&date=2026-11-09&difficulty=intermediate")
    assert lb_res.status_code == 200
    lb = lb_res.json()["leaderboard"]
    assert len(lb) == 2
    assert lb[0]["user_email"] == "fast@example.com"
    assert lb[0]["rank"] == 1
    assert lb[1]["user_email"] == "slow@example.com"
    assert lb[1]["rank"] == 2


def test_action_center_daily_sync(isolated_fake_db):
    """Ensure winning a daily puzzle marks daily challenge complete."""
    client = _make_client_for_user("daily_user@example.com", "Daily Sweeper")

    # Before game, daily status is incomplete
    before_status = client.get("/api/daily/status?date=2026-11-09")
    assert before_status.status_code == 200
    assert before_status.json()["is_daily_completed"] is False

    # Win daily challenge
    client.post(
        "/api/game/finish",
        json={
            "game_id": "daily_win_123",
            "difficulty": "beginner",
            "mode": "daily",
            "date": "2026-11-09",
            "status": "won",
            "elapsed_seconds": 22,
            "cells_revealed": 71,
        },
    )

    # After winning, status is completed
    after_status = client.get("/api/daily/status?date=2026-11-09")
    assert after_status.status_code == 200
    assert after_status.json()["is_daily_completed"] is True
    assert after_status.json()["beginner_status"] == "won"


def test_game_finish_win_validation(isolated_fake_db):
    """Validate win integrity constraints on /api/game/finish."""
    client = _make_client_for_user("validator@example.com", "Validator")

    # 1. Status won with cells_revealed < safe cells must return 400
    bad_res = client.post(
        "/api/game/finish",
        json={
            "game_id": "cheat_game_1",
            "difficulty": "beginner",
            "mode": "casual",
            "status": "won",
            "elapsed_seconds": 10,
            "cells_revealed": 0,
        },
    )
    assert bad_res.status_code == 400
    assert "Invalid win state" in bad_res.json()["detail"]

    # 2. Status won with elapsed_seconds < 1 must return 400
    bad_time = client.post(
        "/api/game/finish",
        json={
            "game_id": "cheat_game_2",
            "difficulty": "beginner",
            "mode": "casual",
            "status": "won",
            "elapsed_seconds": 0,
            "cells_revealed": 71,
        },
    )
    assert bad_time.status_code == 400
    assert "Invalid elapsed_seconds" in bad_time.json()["detail"]

    # 3. Status won with valid safe cells & elapsed seconds must succeed
    good_res = client.post(
        "/api/game/finish",
        json={
            "game_id": "valid_win_1",
            "difficulty": "beginner",
            "mode": "casual",
            "status": "won",
            "elapsed_seconds": 15,
            "cells_revealed": 71,
        },
    )
    assert good_res.status_code == 200
    assert good_res.json()["status"] == "won"

    # 4. Status lost with 0 cells or 0 elapsed seconds is permitted
    lost_res = client.post(
        "/api/game/finish",
        json={
            "game_id": "lost_game_1",
            "difficulty": "beginner",
            "mode": "casual",
            "status": "lost",
            "elapsed_seconds": 0,
            "cells_revealed": 1,
        },
    )
    assert lost_res.status_code == 200
    assert lost_res.json()["status"] == "lost"

