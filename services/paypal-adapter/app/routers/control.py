"""GET /v1/control/status, POST /v1/control/freeze|unfreeze -- api.md section 4.

Real control_flags DB read/write (as of this wave). This is paypal-adapter's own service-
local kill switch, independent of the static PS_PAYPALADAPTER_MONEY_ENABLED env var -- see
app.ops._money_frozen, which now ORs both: money operations are blocked if EITHER source says
frozen (fail closed, matching resolution's own REFUNDS_FROZEN philosophy).

Auth: require_internal_jwt only, no additional operator-role check here. This endpoint is
itself an internal, service-to-service mirror target -- resolution's own operator-role gate
lives on ITS `PUT /controls/refunds-frozen` (services/resolution/app/routers/controls.py),
which is documented to mirror-push to this endpoint (currently left PENDING there, cross-
service push not yet wired). Adding a redundant human-role check here would break that mirror
call once it is wired, so internal JWT auth is the correct and complete gate for this file.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import control_flags as control_flags_repo
from app.db import get_db
from app.deps import Caller, require_internal_jwt
from app.settings import Settings, get_settings

router = APIRouter(prefix="/v1/control", tags=["control"])


def _status_body(
    flags: control_flags_repo.ControlFlags | None, settings: Settings, trace_id: str
) -> dict[str, Any]:
    if flags is None:
        # Fail closed: unseeded/unreadable row -> frozen=true (should not happen post-
        # migration; defensive only, see app.control_flags.get_control_flags).
        return {
            "money_enabled": False,
            "frozen": True,
            "updated_at": None,
            "env_money_enabled": settings.money_enabled,
            "seeded": False,
            "trace_id": trace_id,
        }
    return {
        "money_enabled": flags.money_enabled,
        "frozen": flags.frozen,
        "updated_at": flags.updated_at.isoformat(),
        "env_money_enabled": settings.money_enabled,
        "seeded": True,
        "trace_id": trace_id,
    }


@router.get("/status")
async def control_status(
    _caller: Caller = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    flags = await control_flags_repo.get_control_flags(session)
    return JSONResponse(status_code=200, content=_status_body(flags, settings, str(uuid.uuid4())))


@router.post("/freeze")
async def control_freeze(
    _caller: Caller = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    flags = await control_flags_repo.set_frozen(session, frozen=True)
    if flags is None:
        raise HTTPException(status_code=503, detail="CONTROL_FLAGS_ROW_MISSING")
    return JSONResponse(status_code=200, content=_status_body(flags, settings, str(uuid.uuid4())))


@router.post("/unfreeze")
async def control_unfreeze(
    _caller: Caller = Depends(require_internal_jwt),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    flags = await control_flags_repo.set_frozen(session, frozen=False)
    if flags is None:
        raise HTTPException(status_code=503, detail="CONTROL_FLAGS_ROW_MISSING")
    return JSONResponse(status_code=200, content=_status_body(flags, settings, str(uuid.uuid4())))
