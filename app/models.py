"""Pydantic data models for Ottomate Boom API."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class GameStartRequest(BaseModel):
    """Payload to initiate a new Minesweeper game."""

    difficulty: Literal["beginner", "intermediate", "expert"] = "beginner"
    mode: Literal["daily", "casual"] = "daily"
    date: str | None = None
    seed: str | None = None


class GameActionRequest(BaseModel):
    """Payload for live server-side board actions."""

    game_id: str
    action: Literal["reveal", "flag", "chord"]
    row: int
    col: int
    elapsed_seconds: int = 0


class GameFinishRequest(BaseModel):
    """Payload to record completed game results."""

    game_id: str
    difficulty: Literal["beginner", "intermediate", "expert"]
    mode: Literal["daily", "casual"] = "daily"
    date: str | None = None
    seed: str | None = None
    status: Literal["won", "lost"]
    elapsed_seconds: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    cells_revealed: int = Field(default=0, ge=0)
    flags_placed: int = Field(default=0, ge=0)
    three_bv: int = Field(default=0, ge=0)
    first_click: list[int] | None = None


class LeaderboardEntry(BaseModel):
    """Ranked player record on daily or all-time leaderboard."""

    rank: int = 0
    user_email: str
    display_name: str
    difficulty: str = "all"
    games_played: int = 0
    games_won: int = 0
    win_rate: float = 0.0
    best_time_seconds: int | None = None
    best_beginner_seconds: int | None = None
    best_intermediate_seconds: int | None = None
    best_expert_seconds: int | None = None
    avg_time_seconds: float | None = None
    current_streak: int = 0
    max_streak: int = 0
    last_played: str | None = None


class LeaderboardResponse(BaseModel):
    """Aggregated leaderboard response."""

    scope: Literal["daily", "all_time"] = "all_time"
    date: str | None = None
    difficulty: str = "all"
    leaderboard: list[LeaderboardEntry] = Field(default_factory=list)
    my_stats: LeaderboardEntry | None = None


class DifficultyStats(BaseModel):
    """Stats breakdown for a specific difficulty level."""

    played: int = 0
    won: int = 0
    win_rate: float = 0.0
    best_time_seconds: int | None = None
    avg_time_seconds: float | None = None


class UserStatsResponse(BaseModel):
    """Career statistics for the authenticated player."""

    user_email: str
    display_name: str
    games_played: int = 0
    games_won: int = 0
    win_rate: float = 0.0
    current_streak: int = 0
    max_streak: int = 0
    daily_challenges_completed: int = 0
    beginner: DifficultyStats = Field(default_factory=DifficultyStats)
    intermediate: DifficultyStats = Field(default_factory=DifficultyStats)
    expert: DifficultyStats = Field(default_factory=DifficultyStats)


class DailyStatusResponse(BaseModel):
    """Daily challenge completion summary for a specific date."""

    date: str
    beginner_status: str | None = None
    intermediate_status: str | None = None
    expert_status: str | None = None
    is_daily_completed: bool = False
    action_center_synced: bool = False


class HistoryItem(BaseModel):
    """Recent game history row."""

    game_id: str
    date: str | None = None
    mode: str
    difficulty: str
    status: str
    elapsed_seconds: int
    clicks: int
    three_bv: int = 0
    completed_at: str | None = None
