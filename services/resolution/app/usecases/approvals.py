"""Tier-2 single-use approval-link issuance, lookup and signature verification.

Implements resolution/api.md section 3.7 (GET /approvals/{token}, POST /approvals/{token}/consent)
and spec.md section 5 (tier 2: "single-use consent bound to proposal_hash"). Mirrors the shape of
libs/common/safepayai_common/auth/ticket.py's sign_ticket/verify_ticket (token = "tid.expiry.hmac")
but is deliberately NOT that helper: TicketPayload there is scoped to
mandate_id/proposal_hash/amount_minor/currency for the authorization_ticket used at refund
*execution* time (a different, narrower token for a different leg of the flow); an approval
link instead needs to be looked up by itself (no case_id/offer_id known yet when the buyer
clicks it), and libs/common holds zero business logic (CLAUDE.md), so this stays local rather
than widening that shared type. Only a hash of the raw token is ever persisted
(resolution.approvals.token_hash) -- the raw token is returned to the caller once, at issuance,
and never stored.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app import repo
from app.domain.proposal import OfferRecord
from app.settings import settings

_DOMAIN_PREFIX = b"ps-approval-v1."


def _digest(tid: str, proposal_hash: str, expires_epoch: int, key: bytes) -> str:
    msg = _DOMAIN_PREFIX + "|".join([tid, proposal_hash, str(expires_epoch)]).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


async def issue_approval(session: AsyncSession, offer: OfferRecord) -> str:
    """Create an approvals row for a freshly-created tier-2 (APPROVE) offer.

    Inputs: the just-created OfferRecord (tier APPROVE). Output: the single-use raw token --
    never persisted; only its sha256 is stored in approvals.token_hash. Caller is responsible
    for getting this to the buyer (notification channel is out of this task's scope); losing it
    here is a caller bug, not a usecase concern.
    """
    tid = uuid4().hex
    now = repo.now_utc()
    expires_at = now + timedelta(seconds=settings.approval_link_ttl_s)
    expires_epoch = int(expires_at.timestamp())
    key = settings.approval_link_hmac_key.encode()
    digest = _digest(tid, offer.proposal_hash, expires_epoch, key)
    token = f"{tid}.{expires_epoch}.{digest}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    await repo.insert_approval(
        session,
        approval_id=uuid4(),
        tid=tid,
        proposal_id=offer.offer_id,
        proposal_hash=offer.proposal_hash,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    return token


@dataclass(frozen=True, slots=True)
class ApprovalLookup:
    """In-memory view of one approvals row, keyed by a presented token (api.md s3.7)."""

    approval_id: UUID
    tid: str
    proposal_id: UUID
    proposal_hash: str
    status: str  # issued | consumed | revoked
    expires_at: datetime | None


async def lookup_approval(session: AsyncSession, token: str) -> ApprovalLookup | None:
    """Look up the approvals row for a presented token and verify its HMAC as a tamper check.

    Inputs: the raw token from the URL path. Output: ApprovalLookup, or None on a malformed
    token or no matching row (DB-level 404). Status/expiry are intentionally NOT checked here:
    GET /approvals/{token} (preview, 404 APPROVAL_EXPIRED/APPROVAL_REVOKED) and POST
    /approvals/{token}/consent (409 APPROVAL_REPLAY) map those differently, so the router
    decides based on `.status`/`.expires_at`, not this function.
    Security note: the sha256(token) DB lookup is already the primary authentication (a bearer
    token pattern -- finding the row at all proves possession of the exact token). The HMAC
    recheck against the row's own stored proposal_hash is defense in depth against a corrupted
    or hand-crafted token_hash collision, matching ticket.py's binding pattern; it is not the
    only thing standing between an attacker and a hit.
    """
    parts = token.split(".", 2)
    if len(parts) != 3:
        return None
    tid, exp_s, digest = parts
    try:
        expires_epoch = int(exp_s)
    except ValueError:
        return None

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = await repo.get_approval_by_token_hash(session, token_hash)
    if row is None:
        return None

    key = settings.approval_link_hmac_key.encode()
    expected = _digest(tid, row["proposal_hash"], expires_epoch, key)
    if not hmac.compare_digest(expected, digest):
        return None

    return ApprovalLookup(
        approval_id=row["id"],
        tid=row["tid"],
        proposal_id=row["proposal_id"],
        proposal_hash=row["proposal_hash"],
        status=row["status"],
        expires_at=row["expires_at"],
    )
