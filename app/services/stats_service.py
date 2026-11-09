"""Leaderboard and player statistics service for Ottomate Boom."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from ottomate_core.db import (
    database,
    is_daily_completed,
    normalize_email,
    resolve_user_display_names,
    users_database,
)
from ottomate_core.stats import StreakTracker, calculate_win_rate

from app.config import GAMES_COLLECTION
from app.models import (
    DailyStatusResponse,
    DifficultyStats,
    HistoryItem,
    LeaderboardEntry,
    LeaderboardResponse,
    UserStatsResponse,
)
from app.services.minesweeper_engine import validate_date_str


def get_leaderboard_and_stats(
    current_user_email: str,
    scope: Literal["all_time", "daily"] = "all_time",
    date_str: str | None = None,
    difficulty: str = "all",
    db: Any = None,
    users_db: Any = None,
) -> LeaderboardResponse:
    """Aggregate completed Minesweeper games into ranked LeaderboardEntry rows."""
    db = db or database()
    u_db = users_db or users_database()
    valid_date = validate_date_str(date_str)
    me = normalize_email(current_user_email)
    diff_filter = difficulty.strip().lower()

    docs = db.collection(GAMES_COLLECTION).stream()
    records: list[dict[str, Any]] = []
    for doc in docs:
        d = doc.to_dict() or {}
        st = d.get("status")
        if st not in ("won", "lost"):
            continue
        if scope == "daily":
            if d.get("mode") != "daily":
                continue
            if d.get("date") != valid_date:
                continue
        if diff_filter in ("beginner", "intermediate", "expert"):
            if d.get("difficulty") != diff_filter:
                continue
        records.append(d)

    # Sort chronologically so StreakTracker processes attempts in order
    records.sort(
        key=lambda r: (
            str(r.get("date") or ""),
            str(r.get("completed_at") or r.get("created_at") or ""),
            str(r.get("game_id", "")),
        )
    )

    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        email = normalize_email(str(r.get("user_email", "")))
        if email:
            by_user[email].append(r)

    all_emails = set(by_user.keys()) | {me}
    display_names = resolve_user_display_names(all_emails, db=u_db)

    entries: list[LeaderboardEntry] = []
    for email, games in by_user.items():
        games_played = len(games)
        games_won = 0
        winning_times: list[int] = []
        beg_times: list[int] = []
        int_times: list[int] = []
        exp_times: list[int] = []
        outcomes: list[bool] = []
        last_played = None

        for g in games:
            won = g.get("status") == "won"
            outcomes.append(won)
            elapsed = int(g.get("elapsed_seconds", 0))
            diff = str(g.get("difficulty", "beginner")).lower()
            last_played = g.get("completed_at") or g.get("created_at")

            if won:
                games_won += 1
                winning_times.append(elapsed)
                if diff == "beginner":
                    beg_times.append(elapsed)
                elif diff == "intermediate":
                    int_times.append(elapsed)
                elif diff == "expert":
                    exp_times.append(elapsed)

        win_rate = calculate_win_rate(games_won, games_played)
        streak_info = StreakTracker.compute_streak(outcomes)
        curr_streak = streak_info["count"] if streak_info["type"] == "W" else 0
        best_win_streak = StreakTracker.compute_best_win_streak(outcomes)

        best_time = min(winning_times) if winning_times else None
        avg_time = round(sum(winning_times) / len(winning_times), 1) if winning_times else None

        entries.append(
            LeaderboardEntry(
                rank=0,
                user_email=email,
                display_name=display_names.get(email) or email.split("@")[0],
                difficulty=diff_filter,
                games_played=games_played,
                games_won=games_won,
                win_rate=win_rate,
                best_time_seconds=best_time,
                best_beginner_seconds=min(beg_times) if beg_times else None,
                best_intermediate_seconds=min(int_times) if int_times else None,
                best_expert_seconds=min(exp_times) if exp_times else None,
                avg_time_seconds=avg_time,
                current_streak=curr_streak,
                max_streak=best_win_streak,
                last_played=last_played,
            )
        )

    # Sort leaderboard
    if scope == "daily":
        # For daily: Won games first -> fastest time -> fewest clicks -> name
        entries.sort(
            key=lambda e: (
                -e.games_won,
                e.best_time_seconds if e.best_time_seconds is not None else 999999,
                -e.win_rate,
                e.display_name.lower(),
            )
        )
    else:
        # For all-time: Most wins -> highest win rate -> best time -> name
        entries.sort(
            key=lambda e: (
                -e.games_won,
                -e.win_rate,
                e.best_time_seconds if e.best_time_seconds is not None else 999999,
                -e.games_played,
                e.display_name.lower(),
            )
        )

    my_stats: LeaderboardEntry | None = None
    for idx, entry in enumerate(entries, start=1):
        entry.rank = idx
        if entry.user_email == me:
            my_stats = entry

    if my_stats is None:
        my_stats = LeaderboardEntry(
            rank=0,
            user_email=me,
            display_name=display_names.get(me) or me.split("@")[0],
            difficulty=diff_filter,
        )

    return LeaderboardResponse(
        scope=scope,
        date=valid_date if scope == "daily" else None,
        difficulty=diff_filter,
        leaderboard=entries,
        my_stats=my_stats,
    )


def get_user_stats(
    user_email: str,
    db: Any = None,
    users_db: Any = None,
) -> UserStatsResponse:
    """Compute detailed career statistics for a specific player."""
    db = db or database()
    u_db = users_db or users_database()
    me = normalize_email(user_email)

    display_names = resolve_user_display_names({me}, db=u_db)
    d_name = display_names.get(me) or me.split("@")[0]

    docs = db.collection(GAMES_COLLECTION).where("user_email", "==", me).stream()
    games: list[dict[str, Any]] = []
    for doc in docs:
        d = doc.to_dict() or {}
        st = d.get("status")
        if st in ("won", "lost"):
            games.append(d)

    games.sort(key=lambda g: str(g.get("completed_at") or g.get("created_at") or ""))

    diff_data: dict[str, dict[str, Any]] = {
        "beginner": {"played": 0, "won": 0, "times": []},
        "intermediate": {"played": 0, "won": 0, "times": []},
        "expert": {"played": 0, "won": 0, "times": []},
    }

    total_won = 0
    outcomes: list[bool] = []
    daily_completed_dates: set[str] = set()

    for g in games:
        diff = str(g.get("difficulty", "beginner")).lower()
        if diff not in diff_data:
            diff = "beginner"
        won = g.get("status") == "won"
        outcomes.append(won)
        diff_data[diff]["played"] += 1

        if won:
            total_won += 1
            diff_data[diff]["won"] += 1
            diff_data[diff]["times"].append(int(g.get("elapsed_seconds", 0)))
            if g.get("mode") == "daily" and g.get("date"):
                daily_completed_dates.add(str(g.get("date")))

    streak_info = StreakTracker.compute_streak(outcomes)
    curr_streak = streak_info["count"] if streak_info["type"] == "W" else 0
    best_win_streak = StreakTracker.compute_best_win_streak(outcomes)

    def _build_diff_stats(info: dict[str, Any]) -> DifficultyStats:
        p = info["played"]
        w = info["won"]
        times = info["times"]
        wr = calculate_win_rate(w, p)
        best = min(times) if times else None
        avg = round(sum(times) / len(times), 1) if times else None
        return DifficultyStats(
            played=p,
            won=w,
            win_rate=wr,
            best_time_seconds=best,
            avg_time_seconds=avg,
        )

    return UserStatsResponse(
        user_email=me,
        display_name=d_name,
        games_played=len(games),
        games_won=total_won,
        win_rate=calculate_win_rate(total_won, len(games)),
        current_streak=curr_streak,
        max_streak=best_win_streak,
        daily_challenges_completed=len(daily_completed_dates),
        beginner=_build_diff_stats(diff_data["beginner"]),
        intermediate=_build_diff_stats(diff_data["intermediate"]),
        expert=_build_diff_stats(diff_data["expert"]),
    )


def get_daily_status(
    user_email: str,
    date_str: str | None = None,
    db: Any = None,
    users_db: Any = None,
) -> DailyStatusResponse:
    """Retrieve completion status for Beginner, Intermediate, and Expert on a daily puzzle."""
    db = db or database()
    valid_date = validate_date_str(date_str)
    me = normalize_email(user_email)

    docs = (
        db.collection(GAMES_COLLECTION)
        .where("user_email", "==", me)
        .where("mode", "==", "daily")
        .where("date", "==", valid_date)
        .stream()
    )

    statuses: dict[str, str] = {}
    for doc in docs:
        d = doc.to_dict() or {}
        diff = str(d.get("difficulty", "")).lower()
        st = d.get("status")
        if diff in ("beginner", "intermediate", "expert") and st in ("won", "lost"):
            # If already won, preserve "won"
            if statuses.get(diff) != "won":
                statuses[diff] = st

    is_completed = any(st == "won" for st in statuses.values()) or is_daily_completed(
        "boom", me, valid_date
    )

    return DailyStatusResponse(
        date=valid_date,
        beginner_status=statuses.get("beginner"),
        intermediate_status=statuses.get("intermediate"),
        expert_status=statuses.get("expert"),
        is_daily_completed=is_completed,
    )


def get_player_history(
    user_email: str,
    limit: int = 50,
    db: Any = None,
) -> list[HistoryItem]:
    """Retrieve recent game history for a player."""
    db = db or database()
    me = normalize_email(user_email)

    docs = (
        db.collection(GAMES_COLLECTION)
        .where("user_email", "==", me)
        .stream()
    )

    items: list[HistoryItem] = []
    for doc in docs:
        d = doc.to_dict() or {}
        st = d.get("status")
        if st in ("won", "lost"):
            items.append(
                HistoryItem(
                    game_id=d.get("game_id", doc.id),
                    date=d.get("date"),
                    mode=d.get("mode", "casual"),
                    difficulty=d.get("difficulty", "beginner"),
                    status=st,
                    elapsed_seconds=int(d.get("elapsed_seconds", 0)),
                    clicks=int(d.get("clicks", 0)),
                    three_bv=int(d.get("three_bv", 0)),
                    completed_at=d.get("completed_at") or d.get("created_at"),
                )
            )

    items.sort(
        key=lambda x: str(x.completed_at or ""),
        reverse=True,
    )
    return items[: max(1, min(limit, 200))]
