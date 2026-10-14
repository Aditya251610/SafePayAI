"""Mints the authorization_ticket paypal-adapter verifies on refund_capture (spec.md
section 5; libs/common/safepayai_common/auth/ticket.py is the shared primitive).
resolution holds PS_RESOLUTION_TICKET_HMAC_KEY/_KID; paypal-adapter verifies against the
same key, selected by resolution's own verified caller identity, never by a
client-supplied kid.
"""

from __future__ import annotations

import time

from safepayai_common.auth.ticket import TicketPayload, sign_ticket

from app.settings import settings


def mint_ticket(
    *, mandate_id: str, proposal_hash: str, amount_minor: int, currency: str
) -> str | None:
    """Returns None if no signing key is configured (caller must fail closed on that --
    paypal-adapter rejects a missing/invalid ticket)."""
    if not settings.ticket_hmac_key:
        return None
    expires_at = int(time.time()) + settings.ticket_ttl_seconds
    payload = TicketPayload(
        mandate_id=mandate_id,
        proposal_hash=proposal_hash,
        amount_minor=amount_minor,
        currency=currency,
        expires_at=expires_at,
    )
    return sign_ticket(
        payload, settings.ticket_hmac_key.encode(), settings.ticket_hmac_kid
    )
