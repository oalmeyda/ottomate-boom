"""Configuration and environment settings for Ottomate Boom."""

from __future__ import annotations

import os
from pathlib import Path

from ottomate_core.config import configure_service

VERSION = "2.0.0"
SERVICE_NAME = "ottomate-boom"
APP_TITLE = "Ottomate Boom"

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "boom")

GAMES_COLLECTION = "boom_games"
STATS_COLLECTION = "boom_stats"
USERS_COLLECTION = "users"

SERVICE_CARD_METADATA = {
    "service_id": "boom",
    "title": "Ottomate Boom",
    "category": "puzzles",
    "category_label": "Strategy Puzzles",
    "tagline": "Classic Minesweeper Daily & Speed Challenge",
    "url": "https://ottomate-boom.web.app",
    "icon": "💣",
    "description": "Classic Minesweeper puzzle challenge featuring Beginner (9x9, 10 mines), Intermediate (16x16, 40 mines), and Expert (30x16, 99 mines) boards with daily deterministic challenges, chord clicking, flag counters, customizable cell sizes, and global leaderboards.",
    "tags": ["Minesweeper", "Daily Challenge", "3 Board Sizes", "Leaderboards"],
    "highlight": "New",
    "color": "#ef4444",
    "launched_at": "2026-11-09",
}

# Register service identity and catalog metadata with ottomate-core
configure_service(SERVICE_NAME, FIRESTORE_DATABASE, metadata=SERVICE_CARD_METADATA)


def dev_mode_enabled() -> bool:
    return os.getenv("DEV_MODE", "0").lower() in ("1", "true", "yes")


def google_client_id() -> str:
    return os.getenv(
        "GOOGLE_CLIENT_ID",
        "579098179038-qpe2ofekqke3apb5g6u3jm8o377uhfam.apps.googleusercontent.com",
    )


def organizer_emails() -> list[str]:
    raw = os.getenv("ORGANIZER_EMAILS", "admin@example.com")
    return [e.strip().lower() for e in raw.split(",") if e.strip()]
