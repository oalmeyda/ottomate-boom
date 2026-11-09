"""Pytest fixtures for Ottomate Boom."""

from __future__ import annotations

from ottomate_core.testing import (
    FakeDatabase,
    use_database,
    use_organizers,
    use_users_database,
)
import pytest


@pytest.fixture(autouse=True)
def isolated_fake_db(monkeypatch):
    """Ensure every test runs against an isolated in-memory FakeDatabase by default."""
    fake_db = FakeDatabase()
    fake_users_db = FakeDatabase()
    use_database(monkeypatch, fake_db)
    use_users_database(monkeypatch, fake_users_db)
    use_organizers(monkeypatch, ["admin@example.com"])
    return fake_db
