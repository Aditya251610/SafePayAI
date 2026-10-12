"""POST /classify, /draft, /brief per triage-ai/api.md sections 1-3.

Wave 5: real pipeline. Untrusted-text handling (app/untrusted.py), the LLM gateway call
(app/llm_provider.py's real Gemini/Groq adapters), fail-closed routing, the regex gate
(app/gate.py), and the reviewer brief's field-citation discipline all live in app/service.py
- this router is thin: auth, idempotency lookup, call service, persist, emit outbox, return.
Caller allowlist (resolution only) is enforced via deps.py. Model/provider failures are
NEVER transport errors (api.md section 0) - they return HTTP 200 with a fail-closed payload,
which app/service.py already guarantees by construction.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends
from safepayai_common.llm.gateway import LLMGateway
from sqlalchemy.ext.asyncio import AsyncSession

from app import repo, service
from app.db import get_session
from app.deps import require_resolution_caller
from app.llm_provider import build_gateway
from app.schemas.triage import (
    BriefRequest,
    BriefResponse,
    ClassifyRequest,
    ClassifyResponse,
    DraftRequest,
    DraftResponse,
)
from app.settings import Settings, settings

router = APIRouter(tags=["triage"])


@lru_cache(maxsize=1)
def get_gateway() -> LLMGateway:
    # Constructing a gateway never makes a network call (provider __init__ just stores the
    # key/model); caching it avoids rebuilding client objects on every request. Tests override
    # this via FastAPI's `app.dependency_overrides`, never by mutating the cache.
    return build_gateway(settings)


def get_settings() -> Settings:
    return settings


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    body: ClassifyRequest,
    claims: dict = Depends(require_resolution_caller),
    session: AsyncSession = Depends(get_session),
    cfg: Settings = Depends(get_settings),
    gateway: LLMGateway = Depends(get_gateway),
) -> ClassifyResponse:
    in_hash = service.classify_input_hash(body, cfg)

    existing = await repo.find_existing(
        session,
        case_id=str(body.case_id),
        task="classify",
        input_sha256=in_hash,
        prompt_version=cfg.prompt_version,
    )
    if existing is not None:
        return _replay_classify(existing, cfg)

    response, log_fields = await service.classify(body, cfg, gateway)
    # No explicit `async with session.begin()`: the `find_existing` read above already
    # auto-began a transaction on this session (SQLAlchemy 2.0 async autobegin-on-first-use)
    # -- starting a second explicit one here raises "A transaction is already begun on this
    # Session." Reuse that transaction and commit it once, after both writes (ADR-003: log +
    # outbox in the same transaction).
    await repo.insert_triage_log(session, log_fields)
    await repo.insert_outbox_event(
        session,
        event_type="triage.completed",
        aggregate_id=str(body.case_id),
        payload={
            "triage_id": str(response.triage_id),
            "case_id": str(body.case_id),
            "task": "classify",
            "category": response.category,
            "confidence": response.confidence,
            "route": response.route,
            "reasons": response.reasons,
            "flag_codes": [f.code for f in response.timeline_flags],
        },
        trace_id=body.trace_id,
    )
    await session.commit()
    return response


@router.post("/draft", response_model=DraftResponse)
async def draft(
    body: DraftRequest,
    claims: dict = Depends(require_resolution_caller),
    session: AsyncSession = Depends(get_session),
    cfg: Settings = Depends(get_settings),
    gateway: LLMGateway = Depends(get_gateway),
) -> DraftResponse:
    response, log_fields = await service.draft(body, cfg, gateway)
    async with session.begin():
        await repo.insert_triage_log(session, log_fields)
    return response


@router.post("/brief", response_model=BriefResponse)
async def brief(
    body: BriefRequest,
    claims: dict = Depends(require_resolution_caller),
    session: AsyncSession = Depends(get_session),
    cfg: Settings = Depends(get_settings),
    gateway: LLMGateway = Depends(get_gateway),
) -> BriefResponse:
    # Read-only by construction: no write path to any other service's data exists in this
    # function (or anywhere in this router) - the only DB write here is this service's own
    # append-only triage_log, never a mutation of order/mandate/case state (spec.md section 8).
    response, log_fields = await service.brief(body, cfg, gateway)
    async with session.begin():
        await repo.insert_triage_log(session, log_fields)
    return response


def _replay_classify(row: dict, cfg: Settings) -> ClassifyResponse:
    # Note: `reasons`/`flags` come back from asyncpg already decoded to native Python
    # list/dict (SQLAlchemy's asyncpg dialect registers a jsonb codec connection-wide, which
    # applies even to raw `text()` queries like repo.find_existing's - no manual json.loads
    # needed on the read path; the write path still needs json.dumps because the encode
    # direction has no declared bind-parameter type to trigger it, see repo.py).
    from app.schemas.triage import InconsistencyFlag, Provenance

    return ClassifyResponse(
        triage_id=row["triage_id"],
        category=row["category"] or "OTHER",
        confidence=row["confidence"] or 0.0,
        route=row["route"] or "HUMAN_REVIEW",
        reasons=row["reasons"] or ["OK"],
        timeline_flags=[InconsistencyFlag(**f) for f in (row["flags"] or [])],
        provenance=Provenance(
            source="cached",
            model=row["model"],
            prompt_version=cfg.prompt_version,
            cached_at=row["created_at"],
            latency_ms=row["latency_ms"] or 0,
        ),
    )
