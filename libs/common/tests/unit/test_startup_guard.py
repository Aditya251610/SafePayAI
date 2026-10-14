"""Unit tests for the placeholder-secret startup guard."""

from __future__ import annotations

import pytest
from safepayai_common.startup_guard import assert_no_placeholder_secrets


def test_none_and_empty_values_pass() -> None:
    assert_no_placeholder_secrets({"A": None, "B": ""})


def test_real_value_passes() -> None:
    assert_no_placeholder_secrets({"A": "a-real-generated-256-bit-key"})


@pytest.mark.parametrize(
    "value",
    [
        "changeme",
        "changeme-local-dev-only",
        "CHANGEME-SHARED-CRON-SECRET",
        "  changeme  ",
    ],
)
def test_placeholder_prefix_raises(value: str) -> None:
    with pytest.raises(RuntimeError, match="placeholder secret"):
        assert_no_placeholder_secrets({"A": value})


def test_substring_not_prefix_does_not_raise() -> None:
    # A DB URL with "changeme" as a path segment, not a prefix, must not false-positive.
    assert_no_placeholder_secrets(
        {"A": "postgresql+asyncpg://svc_checkout:changeme@localhost:5432/artiq"}
    )


def test_error_names_every_offending_var() -> None:
    with pytest.raises(RuntimeError, match="A, B"):
        assert_no_placeholder_secrets({"A": "changeme", "B": "changeme-x", "C": "real"})
