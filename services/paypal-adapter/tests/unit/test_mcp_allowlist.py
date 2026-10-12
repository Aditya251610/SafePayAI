"""L1 unit tests for the MCP per-tool caller allowlist (app/mcp.py, app/deps.py
DEFAULT_ALLOWLIST). No DB needed: a denied caller is rejected before any session/PayPal
call, which is exactly the path under test here (ADR-010/golden rules: only shopping-agent
and triage-ai hold LLM keys, and neither may ever call a paypal-adapter tool).
"""

from __future__ import annotations

import time

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import DEFAULT_ALLOWLIST
from app.main import app
from app.mcp import ALL_TOOLS

TEST_SECRET = "test-only-hs256-secret-not-for-production-use"
TEST_KID = "test-kid"

LLM_HOLDING_SERVICES = ("shopping-agent", "triage-ai")


def _mint(sub: str) -> str:
    now = int(time.time())
    payload = {"sub": sub, "aud": "paypal-adapter", "iat": now, "exp": now + 300}
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256", headers={"kid": TEST_KID})


@pytest.fixture(autouse=True)
def _trusted_issuers(monkeypatch):
    import json

    monkeypatch.setenv(
        "PS_PAYPALADAPTER_INTERNAL_TRUSTED_ISSUERS", json.dumps({TEST_KID: TEST_SECRET})
    )
    monkeypatch.setenv("PS_PAYPALADAPTER_INTERNAL_JWT_AUD", "paypal-adapter")


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _rpc(client, token: str, method: str, params: dict | None = None) -> dict:
    resp = await client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("llm_service", LLM_HOLDING_SERVICES)
async def test_llm_holding_services_see_no_tools(client, llm_service):
    """shopping-agent and triage-ai hold LLM keys (ADR-010) and must never be able to
    call paypal-adapter's money tools -- tools/list must return an empty list for them."""
    token = _mint(llm_service)
    body = await _rpc(client, token, "tools/list")
    assert body["result"]["tools"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("llm_service", LLM_HOLDING_SERVICES)
@pytest.mark.parametrize("tool", ALL_TOOLS)
async def test_llm_holding_services_denied_on_every_tool(client, llm_service, tool):
    """Explicit, tool-by-tool assertion (golden rule): an LLM-holding service is denied on
    EVERY tool in the allowlist, not just the money ones, with NOT_PERMITTED and isError."""
    assert llm_service not in DEFAULT_ALLOWLIST.get(tool, set()), (
        f"{llm_service} must not be in the allowlist for {tool}"
    )
    token = _mint(llm_service)
    body = await _rpc(client, token, "tools/call", {"name": tool, "arguments": {}})
    result = body["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "NOT_PERMITTED"


@pytest.mark.asyncio
async def test_refund_capture_is_resolution_only(client):
    """checkout may create/capture orders but must NOT be able to call refund_capture or
    get_refund (per the dispatch prompt: "resolution may refund, checkout may not")."""
    checkout_token = _mint("checkout")
    for tool in ("refund_capture", "get_refund"):
        body = await _rpc(client, checkout_token, "tools/call", {"name": tool, "arguments": {}})
        result = body["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "NOT_PERMITTED"


@pytest.mark.asyncio
async def test_add_tracking_is_tracking_only(client):
    resolution_token = _mint("resolution")
    body = await _rpc(
        client, resolution_token, "tools/call", {"name": "add_tracking", "arguments": {}}
    )
    result = body["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "NOT_PERMITTED"


@pytest.mark.asyncio
async def test_unauthenticated_call_rejected(client):
    resp = await client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    assert resp.status_code == 401
