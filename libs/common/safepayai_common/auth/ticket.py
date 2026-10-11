"""Single-use authorization_ticket for money-moving MCP tools.

Binds mandate_id + proposal_hash + amount via HMAC. See architecture/agent-and-mcp-design.md
and paypal-adapter/spec.md. Domain-separation prefix is "ps-ticket-v1." (post-rename; was
"mw-ticket-v1." before the SafePayAI rename — do not reintroduce the old prefix).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

DOMAIN_PREFIX = b"ps-ticket-v1."


@dataclass(frozen=True)
class TicketPayload:
    mandate_id: str
    proposal_hash: str
    amount_minor: int
    currency: str
    expires_at: int


def sign_ticket(payload: TicketPayload, hmac_key: bytes, kid: str) -> str:
    msg = DOMAIN_PREFIX + "|".join(
        [payload.mandate_id, payload.proposal_hash, str(payload.amount_minor), payload.currency, str(payload.expires_at)]
    ).encode()
    digest = hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()
    return f"{kid}.{payload.expires_at}.{digest}"


def verify_ticket(token: str, payload: TicketPayload, hmac_key: bytes) -> bool:
    """Caller must separately enforce single-use (consume-once row) and expiry. This only checks the signature."""
    try:
        kid, exp_s, digest = token.split(".", 2)
    except ValueError:
        return False
    if int(exp_s) != payload.expires_at or time.time() > payload.expires_at:
        return False
    msg = DOMAIN_PREFIX + "|".join(
        [payload.mandate_id, payload.proposal_hash, str(payload.amount_minor), payload.currency, str(payload.expires_at)]
    ).encode()
    expected = hmac.new(hmac_key, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, digest)
