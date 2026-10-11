"""Unit tests are pure-function tests (no DB, no app import) - override the
session-wide `_clean_tables` autouse fixture so they don't pay for Postgres setup."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
