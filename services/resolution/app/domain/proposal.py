"""Offer/proposal types and the proposal_hash computation used for consent binding and check #2.

Implements resolution/spec.md section 5 (proposal_hash = SHA-256(JCS-canonical{...}), approval
tiers 0-3) and section 3 T9/T26 (offer ACTIVE / SUPERSEDED). Pure module: hashing and constant-time
comparison only; no DB, no clock. Scaffold only: hash and compare bodies are yours to write.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Action(StrEnum):
    """What the offer does (spec s5 proposal_hash field 'action')."""

    REFUND = "REFUND"
    RESHIP = "RESHIP"


class OfferStatus(StrEnum):
    """Offer lifecycle. ACCEPTED is an inference (I): spec only names ACTIVE, SUPERSEDED and expiry."""

    ACTIVE = "ACTIVE"
    ACCEPTED = "ACCEPTED"  # (I) not named in spec; needed to make accept idempotent
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class ApprovalTier(StrEnum):
    """Pre-authorization tiers (spec s5 table). REVIEW means the reviewer path; no execution."""

    AUTO = "AUTO"  # tier 0
    CONFIRM = "CONFIRM"  # tier 1, one authenticated click
    APPROVE = "APPROVE"  # tier 2, single-use link bound to proposal_hash
    REVIEW = "REVIEW"  # tier 3


@dataclass(frozen=True, slots=True)
class ProposalFields:
    """Exact fields hashed into proposal_hash (spec s5). Any change must produce a different hash."""

    case_id: UUID
    order_id: UUID
    capture_id: str
    mandate_id: str
    terms_hash: str
    policy_version: str
    action: Action
    amount_minor: int  # integer minor units only (CLAUDE.md money rule)
    currency: str  # from capture, never from client
    offer_seq: int


def proposal_hash(fields: ProposalFields) -> str:
    """Return SHA-256 hex of the JCS (RFC 8785) canonical JSON of `fields` (spec s5).

    Inputs: ProposalFields built from DB rows (never from client input).
    Output: 64-char lowercase hex digest.
    Edge cases: key order and number formatting must be canonical so the same facts always hash
    the same; recomputed at consent and again as check #2 at execution (spec s5, s6).
    """
    raw: dict[str, object] = {
        "case_id": str(fields.case_id),
        "order_id": str(fields.order_id),
        "capture_id": fields.capture_id,
        "mandate_id": fields.mandate_id,
        "terms_hash": fields.terms_hash,
        "policy_version": fields.policy_version,
        "action": fields.action.value,
        "amount_minor": fields.amount_minor,
        "currency": fields.currency,
        "offer_seq": fields.offer_seq,
    }
    # canon.v1-style canonicalization (mirrors services/mandate/app/crypto.py
    # canonical_json_bytes; not a full RFC 8785 conformance claim, spec s5 I):
    # sorted keys by code point, no whitespace, UTF-8, no floats.
    canonical = json.dumps(
        raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hashes_match(stored_hex: str, recomputed_hex: str) -> bool:
    """Compare two proposal hashes in constant time.

    Inputs: stored hash from offers/approvals and freshly recomputed hash.
    Output: True only if equal. Edge cases: different lengths -> False; use a constant-time compare.
    """
    if len(stored_hex) != len(recomputed_hex):
        return False
    return hmac.compare_digest(stored_hex, recomputed_hex)


@dataclass(frozen=True, slots=True)
class OfferRecord:
    """In-memory view of one offers row (spec s2 / api GET /cases offer block)."""

    offer_id: UUID
    case_id: UUID
    offer_seq: int
    action: Action
    amount_minor: int
    currency: str
    tier: ApprovalTier
    status: OfferStatus
    proposal_hash: str
    terms_hash: str
    policy_version: str
