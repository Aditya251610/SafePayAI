"""Non-UUID {mandate_id} path params are a clean 404, not a 500 (uuid-cast error)."""

from __future__ import annotations

import pytest

from app_mandate.deps import valid_mandate_id
from app_mandate.errors import MandateError


def test_valid_uuid_passes_through():
    u = "123e4567-e89b-12d3-a456-426614174000"
    assert valid_mandate_id(u) == u


@pytest.mark.parametrize("bad", ["not-a-uuid", "123", "", "abc/def"])
def test_non_uuid_is_404(bad):
    with pytest.raises(MandateError) as ei:
        valid_mandate_id(bad)
    assert ei.value.status_code == 404
    assert ei.value.code == "MANDATE_NOT_FOUND"


def test_route_returns_404_envelope_for_non_uuid():
    from fastapi.testclient import TestClient

    from app_mandate.main import app

    r = TestClient(app, raise_server_exceptions=False).get("/mandates/not-a-uuid")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "MANDATE_NOT_FOUND"
