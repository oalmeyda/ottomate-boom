"""FastAPI entry point for Ottomate Boom."""

from __future__ import annotations

from ottomate_core.api import create_ottomate_app

from app.api.boom_router import router as boom_router
from app.config import (
    APP_TITLE,
    SERVICE_NAME,
    STATIC_DIR,
    VERSION,
)

app = create_ottomate_app(
    title=APP_TITLE,
    description="Ottomate Boom: Classic Minesweeper with Daily Challenges & Leaderboards",
    version=VERSION,
    service_name=SERVICE_NAME,
    static_dir=STATIC_DIR,
    routers=[boom_router],
)
