"""add_tracking / get_tracking / cancel_tracking -- api.md section 4/5.5-5.6. Caller: tracking
(+ resolution for get_tracking) only.

Real PayPal Order Tracking API calls as of this wave. tracker_id is always
`{capture_id}-{tracking_number}` per api.md section 5.5's documented contract/sandbox-spike
example, not parsed off a PayPal response body -- see app.ops._tracker_id. get_tracking's
`carrier_status`/`verified` fields are deliberately honest placeholders (CLAUDE.md honesty
rule) -- see app.ops.get_tracking's own docstring. cancel_tracking only accepts
status=CANCELLED (irreversible) per the same sandbox spike -- ON_HOLD/DELIVERED are rejected
by PayPal itself, not by this adapter.

The contract gap previously flagged here (tracking's add_tracking client posting
`{capture_id, tracking_number, carrier}` with no `request_id`, vs this endpoint's
`extra="forbid"` AddTrackingRequest) has been fixed in services/tracking/app/clients.py as
part of the same integration pass that wired cancel_tracking's endpoint here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app import ops
from app.deps import Caller, require_tool_permission
from app.paypal_client import PayPalClient, get_paypal_client
from app.schemas.orders import AddTrackingRequest, UpdateTrackerStatusRequest

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


@router.patch("/orders/{order_id}/trackers/{tracker_id}/status", status_code=204)
async def cancel_tracking(
    request: Request,
    order_id: str,
    tracker_id: str,
    body: UpdateTrackerStatusRequest,
    _caller: Caller = Depends(require_tool_permission("cancel_tracking")),  # noqa: B008
    client: PayPalClient = Depends(get_paypal_client),
) -> Response:
    trace_id = _trace_id(request)
    try:
        await ops.cancel_tracking(
            client, order_id, tracker_id, status=body.status, trace_id=trace_id
        )
    except ops.OpError as exc:
        return JSONResponse(status_code=exc.http_status, content=ops.error_envelope(exc, trace_id))
    # 204 per the tracking service's own client contract (resp.status_code == 204 check) --
    # no body, matching PayPal's own PATCH response and plain HTTP 204 semantics.
    return Response(status_code=204)
