"""add_tracking / get_tracking -- api.md section 4/5.5-5.6. Caller: tracking only.

Real PayPal Order Tracking API calls as of this wave. tracker_id is always
`{capture_id}-{tracking_number}` per api.md section 5.5's documented contract/sandbox-spike
example, not parsed off a PayPal response body -- see app.ops._tracker_id. get_tracking's
`carrier_status`/`verified` fields are deliberately honest placeholders (CLAUDE.md honesty
rule) -- see app.ops.get_tracking's own docstring.

Known contract gap (flagged, not introduced by this wave): services/tracking/app/clients.py
`add_tracking` posts `{capture_id, tracking_number, carrier}` with no `request_id`, while
`app.schemas.orders.AddTrackingRequest` here requires `request_id` and `carrier_name_other`
(not `carrier`) with `extra="forbid"` -- a real call from `tracking` as currently written
will 422 against this real endpoint (previously it 501'd instead, so this was never visible).
Fixing tracking's own client payload is out of this task's scope (separate service); left for
the integrator to reconcile.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app import ops
from app.deps import Caller, require_tool_permission
from app.paypal_client import PayPalClient, get_paypal_client
from app.schemas.orders import AddTrackingRequest

router = APIRouter(prefix="/v1", tags=["tracking"])


def _trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


@router.post("/orders/{order_id}/track")
async def add_tracking(
    request: Request,
    order_id: str,
    body: AddTrackingRequest,
    _caller: Caller = Depends(require_tool_permission("add_tracking")),  # noqa: B008
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    trace_id = _trace_id(request)
    try:
        envelope = await ops.add_tracking(
            client,
            order_id,
            capture_id=body.capture_id,
            tracking_number=body.tracking_number,
            carrier_name_other=body.carrier_name_other,
            notify_payer=body.notify_payer,
            trace_id=trace_id,
        )
    except ops.OpError as exc:
        return JSONResponse(status_code=exc.http_status, content=ops.error_envelope(exc, trace_id))
    http_status = 200 if envelope.get("replayed") else 201
    return JSONResponse(status_code=http_status, content=envelope)


@router.get("/orders/{order_id}/trackers/{tracker_id}")
async def get_tracking(
    request: Request,
    order_id: str,
    tracker_id: str,
    _caller: Caller = Depends(require_tool_permission("get_tracking")),  # noqa: B008
    client: PayPalClient = Depends(get_paypal_client),
) -> JSONResponse:
    trace_id = _trace_id(request)
    try:
        envelope = await ops.get_tracking(client, order_id, tracker_id, trace_id=trace_id)
    except ops.OpError as exc:
        return JSONResponse(status_code=exc.http_status, content=ops.error_envelope(exc, trace_id))
    return JSONResponse(status_code=200, content=envelope)
