"""POST /internal/events, POST /internal/events/batch -- api.md sec 1.

Append algorithm, canonicalization, advisory-lock linkage and event_id idempotency are
implemented in app/chain/append.py (spec.md sec 3/4). This router: verifies the caller
(already done by the `verify_internal_token` dependency), enforces producer == token.sub
(spec.md sec 5 step 4b), calls the chain module inside a transaction, and maps its
outcomes/exceptions onto api.md sec 1's response codes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.append import (
    ChainConfigurationError,
    EventIdConflict,
    append_batch,
    append_one,
)
from app.db import get_session
from app.deps import ProducerClaims, verify_internal_token
from app.schemas.events import (
    AppendResult,
    BatchItemResult,
    BatchResponse,
    EventBatchRequest,
    EventEnvelope,
)
from app.settings import Settings, get_settings

logger = logging.getLogger("audit.events")

router = APIRouter(prefix="/internal/events", tags=["ingestion"])


@router.post("")
async def append_event(
    envelope: EventEnvelope,
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    if envelope.producer != claims.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "producer_mismatch",
                "detail": "envelope.producer must equal verified token sub",
            },
        )

    attempts = 0
    last_exc: Exception | None = None
    while attempts < max(settings.append_max_retries, 1):
        attempts += 1
        try:
            async with session.begin():
                outcome = await append_one(
                    session, chain_id=settings.chain_id, producer_sub=claims.sub, envelope=envelope
                )
            break
        except EventIdConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "event_id_conflict",
                    "detail": f"event_id already recorded with different content (seq={exc.seq})",
                },
            ) from exc
        except ChainConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "db_unavailable",
                    "detail": "chain not initialized (genesis missing)",
                },
            ) from exc
        except (IntegrityError, DBAPIError) as exc:
            last_exc = exc
            logger.warning(
                "append retry %s/%s after db error: %s", attempts, settings.append_max_retries, exc
            )
            continue
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "chain_busy", "detail": "append retries exhausted"},
        ) from last_exc

    code = status.HTTP_200_OK if outcome.status == "DUPLICATE" else status.HTTP_201_CREATED
    return JSONResponse(
        status_code=code,
        content=AppendResult(
            seq=outcome.seq, row_hash=outcome.row_hash, duplicate=outcome.status == "DUPLICATE"
        ).model_dump(),
    )


@router.post("/batch")
async def append_events_batch(
    body: EventBatchRequest,
    claims: ProducerClaims = Depends(verify_internal_token),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    if len(body.events) > settings.batch_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "batch_too_large", "detail": "exceeds PS_AUDIT_BATCH_MAX"},
        )

    results_by_id: dict[str, BatchItemResult] = {}
    accepted: list[EventEnvelope] = []
    for env in body.events:
        if env.producer != claims.sub:
            results_by_id[env.event_id] = BatchItemResult(
                event_id=env.event_id, status="REJECTED", error="PRODUCER_MISMATCH"
            )
        else:
            accepted.append(env)

    if accepted:
        attempts = 0
        last_exc: Exception | None = None
        while attempts < max(settings.append_max_retries, 1):
            attempts += 1
            try:
                async with session.begin():
                    outcomes = await append_batch(
                        session,
                        chain_id=settings.chain_id,
                        producer_sub=claims.sub,
                        envelopes=accepted,
                    )
                for outcome in outcomes:
                    results_by_id[outcome.event_id] = BatchItemResult(
                        event_id=outcome.event_id,
                        status="APPENDED" if outcome.status == "APPENDED" else "DUPLICATE",
                        seq=outcome.seq,
                    )
                break
            except EventIdConflict as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "event_id_conflict", "detail": f"seq={exc.seq}"},
                ) from exc
            except ChainConfigurationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "db_unavailable",
                        "detail": "chain not initialized (genesis missing)",
                    },
                ) from exc
            except (IntegrityError, DBAPIError) as exc:
                last_exc = exc
                logger.warning(
                    "batch append retry %s/%s after db error: %s",
                    attempts,
                    settings.append_max_retries,
                    exc,
                )
                continue
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "chain_busy", "detail": "batch append retries exhausted"},
            ) from last_exc

    results = [results_by_id[env.event_id] for env in body.events]
    return JSONResponse(status_code=200, content=BatchResponse(results=results).model_dump())
