"""End-to-end /propose and /intent-fit against a real migrated Postgres, with the
catalog/mandate HTTP calls and the LLM gateway mocked (no real network, no real API
keys needed) -- this exercises the actual DB writes (proposal_log + outbox) that unit
tests, which never touch a database, cannot cover."""

from __future__ import annotations

import pytest

from app import clients as clients_module
from app import deps
from app.llm_providers import LLMFailClosedError


async def _fake_require_service_jwt() -> deps.ServicePrincipal:
    return deps.ServicePrincipal(sub="buyer-1", role="buyer", buyer_id="buyer-1")


async def _fake_require_checkout_caller() -> deps.ServicePrincipal:
    return deps.ServicePrincipal(sub="svc:checkout", role="service", buyer_id=None)


@pytest.fixture(autouse=True)
def _patched_auth():
    """FastAPI dependency_overrides, not monkeypatching app.deps directly -- the
    routers imported `require_service_jwt`/`require_checkout_caller` by value, so
    patching the app.deps module attribute would not affect the already-bound Depends()
    default in each route. This bypasses the real JWKS check (no auth-gateway running in
    this test), which is fine: this test exercises /propose and /intent-fit's own logic
    and DB writes, not token verification (that is covered in test_health.py-adjacent
    auth tests elsewhere)."""
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[deps.require_service_jwt] = (
        _fake_require_service_jwt
    )
    fastapi_app.dependency_overrides[deps.require_checkout_caller] = (
        _fake_require_checkout_caller
    )
    yield
    fastapi_app.dependency_overrides.clear()


CATALOG_ITEMS = [
    {
        "sku": "RUN-1",
        "title": "Trail running shoes",
        "category": "fitness",
        "merchant_id": "M1",
        "price_minor": 5500,
        "description": "shoes for running",
    },
]
MANDATE_SUMMARY = {
    "allowed_merchant_ids": ["M1"],
    "max_total_minor": 10000,
    "currency": "USD",
    "expiry": "2026-12-31",
}


@pytest.mark.asyncio
async def test_propose_form_mode_writes_proposal_log_and_outbox(
    client, db_engine, monkeypatch
) -> None:
    async def fake_fetch_catalog_items(**kwargs):
        return CATALOG_ITEMS

    async def fake_fetch_mandate_summary(**kwargs):
        return MANDATE_SUMMARY

    monkeypatch.setattr(clients_module, "fetch_catalog_items", fake_fetch_catalog_items)
    monkeypatch.setattr(
        clients_module, "fetch_mandate_summary", fake_fetch_mandate_summary
    )
    import app.routers.propose as propose_router

    monkeypatch.setattr(propose_router, "fetch_catalog_items", fake_fetch_catalog_items)
    monkeypatch.setattr(
        propose_router, "fetch_mandate_summary", fake_fetch_mandate_summary
    )

    import uuid

    mandate_id = str(uuid.uuid4())
    response = await client.post(
        "/propose",
        json={
            "mandate_id": mandate_id,
            "mode": "form",
            "form": {
                "category": "fitness",
                "max_budget_minor": 6000,
                "quantity": 1,
                "merchant_id": None,
                "keywords": "running",
            },
        },
        headers={"Authorization": "Bearer faketoken"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "OK"
    assert body["source"] == "form"
    assert body["lines"][0]["sku"] == "RUN-1"

    from sqlalchemy import text as sa_text

    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                sa_text(
                    "SELECT count(*) FROM agent.proposal_log WHERE mandate_id = :m"
                ),
                {"m": mandate_id},
            )
        ).scalar_one()
        assert row == 1
        outbox_row = (
            await conn.execute(
                sa_text(
                    "SELECT count(*) FROM agent.outbox WHERE type = 'cart.proposed'"
                )
            )
        ).scalar_one()
        assert outbox_row >= 1


@pytest.mark.asyncio
async def test_propose_get_reads_back_stored_proposal(client, monkeypatch) -> None:
    async def fake_fetch_catalog_items(**kwargs):
        return CATALOG_ITEMS

    async def fake_fetch_mandate_summary(**kwargs):
        return MANDATE_SUMMARY

    import app.routers.propose as propose_router

    monkeypatch.setattr(propose_router, "fetch_catalog_items", fake_fetch_catalog_items)
    monkeypatch.setattr(
        propose_router, "fetch_mandate_summary", fake_fetch_mandate_summary
    )

    import uuid

    mandate_id = str(uuid.uuid4())
    create_response = await client.post(
        "/propose",
        json={
            "mandate_id": mandate_id,
            "mode": "form",
            "form": {
                "category": "fitness",
                "max_budget_minor": 6000,
                "quantity": 1,
                "merchant_id": None,
                "keywords": "running",
            },
        },
        headers={"Authorization": "Bearer faketoken"},
    )
    proposal_id = create_response.json()["proposal_id"]

    get_response = await client.get(
        f"/propose/{proposal_id}", headers={"Authorization": "Bearer faketoken"}
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["proposal_id"] == proposal_id


@pytest.mark.asyncio
async def test_propose_catalog_unavailable_returns_503(client, monkeypatch) -> None:
    import app.routers.propose as propose_router

    async def fake_fetch_mandate_summary(**kwargs):
        return MANDATE_SUMMARY

    async def failing_fetch_catalog_items(**kwargs):
        raise clients_module.CatalogUnavailableError("down")

    monkeypatch.setattr(
        propose_router, "fetch_mandate_summary", fake_fetch_mandate_summary
    )
    monkeypatch.setattr(
        propose_router, "fetch_catalog_items", failing_fetch_catalog_items
    )

    import uuid

    response = await client.post(
        "/propose",
        json={
            "mandate_id": str(uuid.uuid4()),
            "mode": "intent",
            "intent_text": "a mug",
        },
        headers={"Authorization": "Bearer faketoken"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "CATALOG_UNAVAILABLE"


@pytest.mark.asyncio
async def test_intent_fit_degrades_to_needs_confirmation_when_llm_fails(
    client, monkeypatch
) -> None:
    import app.routers.intent_fit as intent_fit_router

    class FailingGateway:
        async def call(self, *args, **kwargs):
            raise LLMFailClosedError("no provider configured")

    monkeypatch.setattr(
        intent_fit_router, "build_fit_gateway", lambda settings: FailingGateway()
    )

    response = await client.post(
        "/intent-fit",
        json={
            "mandate_id": "m1",
            "intent_text": "birthday gift for a runner",
            "cart_lines": [
                {
                    "sku": "RUN-1",
                    "quantity": 1,
                    "title": "Trail running shoes",
                    "category": "fitness",
                }
            ],
        },
        headers={"Authorization": "Bearer faketoken"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "NEEDS_BUYER_CONFIRMATION"
    assert body["degraded"] is True
