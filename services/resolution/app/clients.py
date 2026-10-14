"""Outbound sync calls: mandate (terms), checkout (order/capture facts), tracking (shipment
facts), paypal-adapter (refund_capture/get_refund/reconcile), triage-ai (classify).

spec.md section 1: these are resolution's only downward sync calls. Every function here fails
closed (returns None / a Result with ok=False) on timeout, connection error, 5xx or malformed
response - callers treat that as a missing fact (decide() D0) or an UNKNOWN/FAIL check result,
never a silent pass. Mirrors services/checkout/app/clients.py's Result-object pattern.

Known gap (flagged, not a resolution bug): checkout's current `GET /orders/{id}` response
(services/checkout/app/routers/orders.py `_order_view`) does not yet expose a `captures` block
or `protected_until`; until checkout's Wave 6 adds those, `get_capture_facts` and the
protected_until half of order facts will come back None, which correctly fails closed to
HUMAN_REVIEW (D0) rather than guessing. paypal-adapter's refund/reconcile/get-refund endpoints
(services/paypal-adapter/app/routers/{captures,refunds,reconcile}.py) are themselves still 501
stubs at the time of writing, so `refund_capture`/`get_refund`/`reconcile_refund` will surface
as UNKNOWN until that service implements them - exactly the fail-closed behaviour spec s7/s8
already require for an unreachable adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

from app.deps import mint_outbound_token
from app.domain.policy import CaptureFacts, TermsSnapshot
from app.domain.states import CaseKind
from app.settings import settings


class AdapterResult:
    """Outcome of a paypal-adapter call. `status_code` lets callers map per spec s7's table."""

    def __init__(
        self,
        ok: bool,
        status_code: int | None,
        body: dict[str, Any] | None,
        detail: str,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.body = body
        self.detail = detail


def _client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(timeout_s))


async def get_mandate_terms(
    mandate_id: str, token: str | None = None
) -> tuple[TermsSnapshot | None, str | None, bool]:
    """GET /mandates/{id}/terms. Returns (TermsSnapshot|None, terms_hash|None, hmac_valid).

    None terms = unreachable/malformed/revoked (D0 FACT_UNAVAILABLE). hmac_valid False maps
    to ReasonCode.TERMS_INVALID (spec s4 D0, s6 check 3).

    api.md section 6 (confirmed D1, 00-platform-prd.md): "mandate.revoked blocks
    pre-authorization for cases not yet opened; opened cases keep their terms snapshot."
    Since terms_snapshot is read once and frozen at open_case time (never re-fetched for an
    existing case -- see open_case.py), the only place this rule can be enforced is HERE:
    if the mandate is already revoked/expired/exhausted at the moment a NEW case asks for
    terms, return None (same as unreachable) so open_case freezes no protection for it,
    rather than silently granting full terms to a case opened after revocation.
    """
    token = token or mint_outbound_token("mandate")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.mandate_url, settings.triage_timeout_s) as client:
            resp = await client.get(f"/mandates/{mandate_id}/terms", headers=headers)
    except httpx.HTTPError:
        return None, None, False
    if resp.status_code != 200:
        return None, None, False
    try:
        body = resp.json()
    except ValueError:
        return None, None, False

    if body.get("mandate_status") != "active":
        return None, None, False

    protection = body.get("protection") or {}
    kinds_covered_raw = protection.get("kinds_covered") or []
    kinds_covered: set[CaseKind] = set()
    for k in kinds_covered_raw:
        try:
            kinds_covered.add(CaseKind(k))
        except ValueError:
            continue
    terms = TermsSnapshot(
        kinds_covered=frozenset(kinds_covered),
        max_refund_minor=int(protection.get("max_refund_minor", 0)),
        window_hold_days=int(protection.get("deliver_by_days", 0)),
        rule="FULL_ORDER",
    )
    hmac_valid = body.get("integrity") == "OK"
    terms_hash = body.get("terms_hash")
    return terms, terms_hash, hmac_valid


async def get_capture_facts(
    order_id: str, token: str | None = None
) -> CaptureFacts | None:
    """GET /orders/{order_id} on checkout. None = unreachable or capture facts not exposed yet."""
    token = token or mint_outbound_token("checkout")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.checkout_url, settings.adapter_timeout_s) as client:
            resp = await client.get(f"/orders/{order_id}", headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None

    capture_id = body.get("capture_id") or body.get("paypal_order_id")
    amount_minor = body.get("total_minor")
    currency = body.get("currency")
    if capture_id is None or amount_minor is None or currency is None:
        return None
    # checkout exposes its own order-status vocabulary (CAPTURED/CAPTURE_PENDING/...), not
    # PayPal's capture-status vocabulary that check_capture_identity enforces (COMPLETED/
    # PARTIALLY_REFUNDED). Map the one checkout status that means "captured, refundable"
    # until checkout exposes the real PayPal capture status directly.
    raw_status = str(body.get("capture_status") or body.get("status") or "")
    status = "COMPLETED" if raw_status == "CAPTURED" else raw_status
    return CaptureFacts(
        capture_id=str(capture_id),
        status=status,
        amount_minor=int(amount_minor),
        refunded_total_minor=int(body.get("refunded_total_minor", 0)),
        currency=str(currency),
    )


async def get_order_identity(
    order_id: str, token: str | None = None
) -> tuple[str | None, str | None, str | None]:
    """GET /orders/{order_id} on checkout; returns (mandate_id, capture_id, buyer_id), any may be None."""
    token = token or mint_outbound_token("checkout")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.checkout_url, settings.adapter_timeout_s) as client:
            resp = await client.get(f"/orders/{order_id}", headers=headers)
    except httpx.HTTPError:
        return None, None, None
    if resp.status_code != 200:
        return None, None, None
    try:
        body = resp.json()
    except ValueError:
        return None, None, None
    mandate_id = body.get("mandate_id")
    capture_id = body.get("capture_id") or body.get("paypal_order_id")
    buyer_id = body.get("buyer_id")
    return (
        str(mandate_id) if mandate_id else None,
        str(capture_id) if capture_id else None,
        str(buyer_id) if buyer_id else None,
    )


async def get_protected_until(
    order_id: str, window_hold_days: int, token: str | None = None
) -> Any | None:
    """Demo protection window: checkout's order response has no literal `protected_until`
    field (known gap, flagged in this module's docstring) -- derive it here instead from
    the order's own `created_at` + the mandate's `window_hold_days` (already fetched into
    terms_snapshot by open_case), rather than waiting on a checkout schema change."""
    token = token or mint_outbound_token("checkout")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.checkout_url, settings.adapter_timeout_s) as client:
            resp = await client.get(f"/orders/{order_id}", headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    created_at_raw = body.get("created_at")
    if not created_at_raw:
        return None
    try:
        created_at = datetime.fromisoformat(str(created_at_raw))
    except ValueError:
        return None
    return created_at + timedelta(days=window_hold_days)


@dataclass(frozen=True, slots=True)
class OrderStateFacts:
    """Subset of checkout's GET /orders/{id} needed for triage-ai's OrderFacts.order_date/
    state fields -- NOT the same as CaptureFacts (that one maps checkout's status vocabulary
    to PayPal's capture-status vocabulary; this one keeps checkout's raw status string and
    created_at, which triage-ai's schema wants verbatim)."""

    created_at: datetime
    status: str


async def get_order_state_facts(
    order_id: str, token: str | None = None
) -> OrderStateFacts | None:
    """GET /orders/{order_id} on checkout. None = unreachable/malformed; callers fall back
    to a proxy (case.opened_at) for order_date and capture.status (or "UNKNOWN") for state."""
    token = token or mint_outbound_token("checkout")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.checkout_url, settings.adapter_timeout_s) as client:
            resp = await client.get(f"/orders/{order_id}", headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    created_at_raw = body.get("created_at")
    status = body.get("status")
    if not created_at_raw or not status:
        return None
    try:
        created_at = datetime.fromisoformat(str(created_at_raw))
    except ValueError:
        return None
    return OrderStateFacts(created_at=created_at, status=str(status))


@dataclass(frozen=True, slots=True)
class TrackingFacts:
    carrier_status: str | None
    carrier_agrees: bool | None


async def get_tracking_agreement(
    order_id: str, kind: CaseKind, token: str | None = None
) -> TrackingFacts:
    """GET /shipments/{order_id} on tracking, then verify the kind against our own carrier facts.

    Tracking's contract is known exactly (tracking/api.md): consistency.delivered tells us
    whether the carrier fact disagrees with a LATE/LOST claim (spec s4 D3).
    """
    token = token or mint_outbound_token("tracking")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(settings.tracking_url, settings.adapter_timeout_s) as client:
            resp = await client.get(f"/shipments/{order_id}", headers=headers)
    except httpx.HTTPError:
        return TrackingFacts(carrier_status=None, carrier_agrees=None)
    if resp.status_code != 200:
        return TrackingFacts(carrier_status=None, carrier_agrees=None)
    try:
        body = resp.json()
    except ValueError:
        return TrackingFacts(carrier_status=None, carrier_agrees=None)

    consistency = body.get("consistency") or {}
    delivered = bool(consistency.get("delivered", False))
    shipments = body.get("shipments") or []
    carrier_status = shipments[0].get("status") if shipments else None
    if kind in (CaseKind.LATE, CaseKind.LOST):
        carrier_agrees = not delivered
    else:
        carrier_agrees = True
    return TrackingFacts(carrier_status=carrier_status, carrier_agrees=carrier_agrees)


async def refund_capture(
    *,
    capture_id: str,
    request_id: UUID,
    invoice_id: str,
    amount_minor: int,
    currency: str,
    ticket: str,
    mandate_id: str = "",
    proposal_hash: str = "",
    token: str | None = None,
) -> AdapterResult:
    """POST /captures/{capture_id}/refund on paypal-adapter (spec s7 step 2).

    mandate_id/proposal_hash are sent so paypal-adapter can reconstruct the exact
    TicketPayload it needs for real HMAC ticket verification (RefundCaptureRequest already
    has these as optional fields; this is the first caller to actually populate them)."""
    token = token or mint_outbound_token("paypal-adapter")
    headers = {"PayPal-Request-Id": str(request_id), "X-Authorization-Ticket": ticket}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "request_id": str(request_id),
        "invoice_id": invoice_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "ticket": ticket,
        "mandate_id": mandate_id or None,
        "proposal_hash": proposal_hash or None,
    }
    try:
        async with _client(
            settings.paypal_adapter_url, settings.adapter_timeout_s
        ) as client:
            resp = await client.post(
                f"/captures/{capture_id}/refund", json=payload, headers=headers
            )
    except httpx.TimeoutException as exc:
        return AdapterResult(False, None, None, f"timeout: {exc}")
    except httpx.HTTPError as exc:
        return AdapterResult(False, None, None, f"connection_error: {exc}")
    try:
        envelope = resp.json() if resp.content else None
    except ValueError:
        envelope = None
    # paypal-adapter wraps every response in {ok, status, data, error, ...} (ops._envelope);
    # the refund_id/status/capture_id fields callers need live under "data", not top-level.
    body = (envelope or {}).get("data") if envelope else None
    return AdapterResult(
        resp.status_code in (200, 201),
        resp.status_code,
        body,
        f"status={resp.status_code}",
    )


async def get_refund(refund_id: str, token: str | None = None) -> AdapterResult:
    """GET /refunds/{refund_id} on paypal-adapter (spec s8 item 1)."""
    token = token or mint_outbound_token("paypal-adapter")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(
            settings.paypal_adapter_url, settings.adapter_timeout_s
        ) as client:
            resp = await client.get(f"/refunds/{refund_id}", headers=headers)
    except httpx.HTTPError as exc:
        return AdapterResult(False, None, None, f"connection_error: {exc}")
    try:
        envelope = resp.json() if resp.content else None
    except ValueError:
        envelope = None
    body = (envelope or {}).get("data") if envelope else None
    return AdapterResult(
        resp.status_code == 200, resp.status_code, body, f"status={resp.status_code}"
    )


async def reconcile_refund(request_id: UUID, token: str | None = None) -> AdapterResult:
    """POST /reconcile/{request_id} on paypal-adapter (spec s8 item 2): idempotent replay lookup."""
    token = token or mint_outbound_token("paypal-adapter")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client(
            settings.paypal_adapter_url, settings.adapter_timeout_s
        ) as client:
            resp = await client.post(f"/reconcile/{request_id}", headers=headers)
    except httpx.HTTPError as exc:
        return AdapterResult(False, None, None, f"connection_error: {exc}")
    try:
        envelope = resp.json() if resp.content else None
    except ValueError:
        envelope = None
    body = (envelope or {}).get("data") if envelope else None
    return AdapterResult(
        resp.status_code in (200, 201),
        resp.status_code,
        body,
        f"status={resp.status_code}",
    )


@dataclass(frozen=True, slots=True)
class TriageResult:
    """Parsed triage-ai ClassifyResponse (services/triage-ai/app/schemas/triage.py).

    `route == "PROCEED"` maps to the old `triage_ok=True` semantic; `route ==
    "HUMAN_REVIEW"` maps to `triage_ok=False` (decide.py does this mapping, not here).
    `injection_suspected` has no 1:1 field in ClassifyResponse -- it's a heuristic derived
    from `reasons`/`timeline_flags` (see classify_triage's docstring for the exact rule).
    """

    category: CaseKind
    confidence: float
    route: str  # Literal["PROCEED", "HUMAN_REVIEW"]
    reasons: list[str]
    injection_suspected: bool


async def classify_triage(
    *,
    case_id: UUID,
    trace_id: str,
    origin: str,
    buyer_text: str | None,
    timeline: list[dict[str, Any]],
    order: dict[str, Any],
    token: str | None = None,
) -> TriageResult | None:
    """POST /classify on triage-ai (ClassifyRequest in -> ClassifyResponse out, per
    services/triage-ai/app/schemas/triage.py -- the authoritative, already-implemented
    contract). None = unreachable, non-200, or malformed/unparseable response; callers
    (decide.py) treat that as a missing fact and fail closed to HUMAN_REVIEW (spec s4 D1).

    `origin` must already be the lowercase triage-ai vocabulary ("buyer_report"/"detector"),
    `order` an OrderFacts-shaped dict, `timeline` a list of TimelineEvent-shaped dicts --
    decide.py assembles these (business logic stays out of this client module).
    """
    if not settings.triage_ai_url:
        return None
    token = token or mint_outbound_token("triage-ai")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {
        "case_id": str(case_id),
        "trace_id": trace_id,
        "origin": origin,
        "buyer_text": buyer_text,
        "timeline": timeline,
        "order": order,
    }
    try:
        async with _client(settings.triage_ai_url, settings.triage_timeout_s) as client:
            resp = await client.post("/classify", json=payload, headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None

    category_raw = body.get("category")
    try:
        category = CaseKind(category_raw) if category_raw else None
    except ValueError:
        category = None
    route = body.get("route")
    confidence = body.get("confidence")
    reasons_raw = body.get("reasons")
    reasons = [str(r) for r in reasons_raw] if isinstance(reasons_raw, list) else []
    timeline_flags_raw = body.get("timeline_flags")
    timeline_flags = timeline_flags_raw if isinstance(timeline_flags_raw, list) else []

    if category is None or route not in ("PROCEED", "HUMAN_REVIEW"):
        return None
    if not isinstance(confidence, (int, float)):
        return None

    # Heuristic mapping for injection_suspected (no such field in ClassifyResponse):
    # true if any reason string mentions "injection", OR any timeline_flags entry is a
    # WARN-severity InconsistencyFlag (both are triage-ai's existing signals for "don't
    # trust this at face value" -- WARN vs INFO severity is triage-ai's own distinction,
    # per services/triage-ai/app/schemas/triage.py InconsistencyFlag).
    injection_suspected = any("injection" in r.lower() for r in reasons) or any(
        isinstance(flag, dict) and flag.get("severity") == "WARN"
        for flag in timeline_flags
    )

    return TriageResult(
        category=category,
        confidence=float(confidence),
        route=str(route),
        reasons=reasons,
        injection_suspected=injection_suspected,
    )
