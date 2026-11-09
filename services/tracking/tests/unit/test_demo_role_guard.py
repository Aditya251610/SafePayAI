"""Demo clock/force routes: sandbox flags first, then a demo-driving role (merchant or operator)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app_tracking.routers import demo


@pytest.fixture
def sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo.settings, "sandbox_mode", True)
    monkeypatch.setattr(demo.settings, "demo_controls_enabled", True)


@pytest.mark.parametrize("role", ["merchant", "operator"])
def test_demo_roles_pass(sandbox: None, role: str) -> None:
    demo._require_sandbox({"act": {"role": role}})


@pytest.mark.parametrize("role", ["buyer", "reviewer", None])
def test_other_roles_are_403(sandbox: None, role: str | None) -> None:
    with pytest.raises(HTTPException) as exc:
        demo._require_sandbox({"act": {"role": role}})
    assert exc.value.status_code == 403
    assert exc.value.detail == "ROLE_NOT_ALLOWED"


def test_sandbox_flag_off_is_404_before_role_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(demo.settings, "sandbox_mode", False)
    with pytest.raises(HTTPException) as exc:
        demo._require_sandbox({"act": {"role": "operator"}})
    assert exc.value.status_code == 404
