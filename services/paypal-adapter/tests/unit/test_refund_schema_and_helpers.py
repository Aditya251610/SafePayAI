"""L1 unit tests: RefundCaptureRequest accepts resolution's exact Wave 5B payload shape
(services/resolution/app/clients.py `refund_capture`), and small pure-function helpers in
app.ops / app.mcp."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.mcp import _missing
from app.ops import _capture_id_from_links
from app.schemas.orders import RefundCaptureRequest


def test_refund_capture_request_accepts_resolutions_exact_payload():
    """services/resolution/app/clients.py refund_capture() sends exactly this shape --
    no mandate_id, no proposal_hash, a `ticket` field in the body."""
    body = {
        "request_id": str(uuid.uuid4()),
        "invoice_id": "ord_1",
        "amount_minor": 500,
        "currency": "USD",
        "ticket": "opaque-ticket-value",
    }
    req = RefundCaptureRequest(**body)
    assert req.ticket == "opaque-ticket-value"
    assert req.mandate_id is None
    assert req.proposal_hash is None


def test_refund_capture_request_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        RefundCaptureRequest(
            request_id=str(uuid.uuid4()),
            amount_minor=500,
            currency="USD",
            unexpected_field="nope",
        )


def test_capture_id_from_links_parses_up_rel():
    links = [
        {"rel": "self", "href": "https://api.example.com/v2/payments/refunds/R1"},
        {"rel": "up", "href": "https://api.example.com/v2/payments/captures/CAP1"},
    ]
    assert _capture_id_from_links(links) == "CAP1"


def test_capture_id_from_links_none_when_missing():
    assert _capture_id_from_links([]) is None
    assert _capture_id_from_links([{"rel": "self", "href": "x"}]) is None


def test_missing_returns_first_missing_field_name():
    assert _missing({"a": 1}, "a", "b") == "b"
    assert _missing({"a": 1, "b": 2}, "a", "b") is None
    assert _missing({"a": ""}, "a") == "a"
