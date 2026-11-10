"""Minesweeper API router for Ottomate Boom."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from ottomate_core.auth import User, get_current_user
from ottomate_core.db import (
    database,
    record_daily_completed,
    sync_daily_pending_action,
)
from ottomate_core.deps import resolve_acting_target

from app.config import GAMES_COLLECTION
from app.models import (
    DailyStatusResponse,
    GameActionRequest,
    GameFinishRequest,
    GameStartRequest,
    HistoryItem,
    LeaderboardResponse,
    UserStatsResponse,
)
from app.services.minesweeper_engine import (
    DIFFICULTY_CONFIGS,
    MinesweeperBoard,
    validate_date_str,
)
from app.services.stats_service import (
    get_daily_status,
    get_leaderboard_and_stats,
    get_player_history,
    get_user_stats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["boom"])

# In-memory board cache for active live sessions (falls back to Firestore)
_ACTIVE_BOARDS: dict[str, MinesweeperBoard] = {}


def _resolve_target_email(user: User, requested_email: str | None = None) -> str:
    return resolve_acting_target(user, requested_email, action="play")


def sync_boom_pending_action(target_email: str, date_str: str, is_completed: bool = False) -> None:
    """Synchronize Minesweeper challenge completion with the Ottomate Hub Action Center."""
    try:
        if is_completed:
            record_daily_completed("boom", target_email, date_str)
        sync_daily_pending_action(
            service_id="boom",
            user_id=target_email,
            date_str=date_str,
            is_completed=is_completed,
            title="Ottomate Boom",
            subtitle=f"Daily Minesweeper ({date_str})",
            message="Today's Minesweeper board is waiting to be cleared!",
            url="https://ottomate-boom.web.app",
            icon="💣",
        )
    except Exception as exc:
        logger.warning("Action center sync failed for %s: %s", target_email, exc)


@router.post("/game/new")
def start_new_game(
    req: GameStartRequest,
    user: User = Depends(get_current_user),
    db: Any = None,
) -> dict[str, Any]:
    """Initialize a new casual or daily Minesweeper game."""
    target_email = _resolve_target_email(user)
    date_str = validate_date_str(req.date) if req.mode == "daily" else None
    difficulty = req.difficulty.lower().strip()
    if difficulty not in DIFFICULTY_CONFIGS:
        difficulty = "beginner"

    game_id = f"boom_{uuid.uuid4().hex[:12]}"
    board = MinesweeperBoard(
        difficulty=difficulty,
        seed=req.seed,
        is_daily=(req.mode == "daily"),
        date_str=date_str,
    )
    _ACTIVE_BOARDS[game_id] = board

    db = db or database()
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "game_id": game_id,
        "user_email": target_email,
        "mode": req.mode,
        "difficulty": difficulty,
        "date": date_str,
        "seed": board.seed,
        "status": "in_progress",
        "rows": board.rows,
        "cols": board.cols,
        "mines": board.mine_count,
        "three_bv": board.three_bv,
        "elapsed_seconds": 0,
        "clicks": 0,
        "created_at": now_iso,
    }
    db.collection(GAMES_COLLECTION).document(game_id).set(record)

    # Sync daily pending action in Action Center
    if req.mode == "daily" and date_str:
        sync_boom_pending_action(target_email, date_str, is_completed=False)

    state = board.to_client_state()
    state["game_id"] = game_id
    state["user_email"] = target_email
    return state


@router.post("/game/action")
def execute_game_action(
    req: GameActionRequest,
    user: User = Depends(get_current_user),
    db: Any = None,
) -> dict[str, Any]:
    """Execute live reveal, flag, or chord action on an active game board."""
    target_email = _resolve_target_email(user)
    board = _ACTIVE_BOARDS.get(req.game_id)
    db = db or database()

    if not board:
        # Check Firestore to verify game existence
        doc = db.collection(GAMES_COLLECTION).document(req.game_id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Game not found")
        data = doc.to_dict() or {}
        if data.get("user_email") != target_email:
            raise HTTPException(status_code=403, detail="Not authorized for this game")
        board = MinesweeperBoard(
            difficulty=data.get("difficulty", "beginner"),
            seed=data.get("seed"),
            is_daily=(data.get("mode") == "daily"),
            date_str=data.get("date"),
        )
        _ACTIVE_BOARDS[req.game_id] = board

    board.elapsed_seconds = max(board.elapsed_seconds, req.elapsed_seconds)

    if req.action == "reveal":
        res = board.reveal(req.row, req.col)
    elif req.action == "flag":
        res = board.toggle_flag(req.row, req.col)
    elif req.action == "chord":
        res = board.chord(req.row, req.col)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Action failed"))

    # If game ended, record completion
    if board.status in ("won", "lost"):
        now_iso = datetime.now(timezone.utc).isoformat()
        db.collection(GAMES_COLLECTION).document(req.game_id).update(
            {
                "status": board.status,
                "elapsed_seconds": board.elapsed_seconds,
                "clicks": board.clicks,
                "completed_at": now_iso,
            }
        )
        if board.status == "won" and board.is_daily and board.date_str:
            sync_boom_pending_action(target_email, board.date_str, is_completed=True)

    client_state = board.to_client_state()
    client_state["game_id"] = req.game_id
    client_state["user_email"] = target_email
    return client_state


@router.post("/game/finish")
def record_finished_game(
    req: GameFinishRequest,
    user: User = Depends(get_current_user),
    db: Any = None,
) -> dict[str, Any]:
    """Persist completed game outcome from client with statistics and Action Center synchronization."""
    target_email = _resolve_target_email(user)
    db = db or database()
    now_iso = datetime.now(timezone.utc).isoformat()
    valid_date = validate_date_str(req.date) if req.mode == "daily" else None

    doc_ref = db.collection(GAMES_COLLECTION).document(req.game_id)
    doc_data = {
        "game_id": req.game_id,
        "user_email": target_email,
        "mode": req.mode,
        "difficulty": req.difficulty,
        "date": valid_date,
        "seed": req.seed,
        "status": req.status,
        "elapsed_seconds": req.elapsed_seconds,
        "clicks": req.clicks,
        "cells_revealed": req.cells_revealed,
        "flags_placed": req.flags_placed,
        "three_bv": req.three_bv,
        "first_click": req.first_click,
        "completed_at": now_iso,
    }
    doc_ref.set(doc_data, merge=True)

    # Clean up memory cache
    _ACTIVE_BOARDS.pop(req.game_id, None)

    # Sync daily completion
    if req.status == "won" and req.mode == "daily" and valid_date:
        sync_boom_pending_action(target_email, valid_date, is_completed=True)

    return {
        "success": True,
        "game_id": req.game_id,
        "status": req.status,
        "date": valid_date,
        "difficulty": req.difficulty,
        "elapsed_seconds": req.elapsed_seconds,
    }


@router.get("/daily/status", response_model=DailyStatusResponse)
def get_daily_challenge_status(
    date: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Any = None,
    users_db: Any = None,
) -> DailyStatusResponse:
    """Get daily challenge completion state across all 3 sizes for the specified date."""
    target_email = _resolve_target_email(user)
    valid_date = validate_date_str(date)
    res = get_daily_status(target_email, valid_date, db=db, users_db=users_db)
    # Ensure pending action sync
    sync_boom_pending_action(target_email, valid_date, is_completed=res.is_daily_completed)
    res.action_center_synced = True
    return res


@router.get("/leaderboard", response_model=LeaderboardResponse)
def get_leaderboard(
    scope: Literal["all_time", "daily"] = "all_time",
    date: str | None = Query(default=None),
    difficulty: str = Query(default="all"),
    user: User = Depends(get_current_user),
    db: Any = None,
    users_db: Any = None,
) -> LeaderboardResponse:
    """Retrieve daily or all-time ranked leaderboards with personal statistics."""
    target_email = _resolve_target_email(user)
    return get_leaderboard_and_stats(
        current_user_email=target_email,
        scope=scope,
        date_str=date,
        difficulty=difficulty,
        db=db,
        users_db=users_db,
    )


@router.get("/stats", response_model=UserStatsResponse)
def get_current_user_stats(
    user: User = Depends(get_current_user),
    db: Any = None,
    users_db: Any = None,
) -> UserStatsResponse:
    """Retrieve career Minesweeper statistics for the current player."""
    target_email = _resolve_target_email(user)
    return get_user_stats(target_email, db=db, users_db=users_db)


@router.get("/history", response_model=list[HistoryItem])
def get_history(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Any = None,
) -> list[HistoryItem]:
    """Retrieve recent game history for the current player."""
    target_email = _resolve_target_email(user)
    return get_player_history(target_email, limit=limit, db=db)
