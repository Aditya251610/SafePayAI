"""Pure functions for the cart check pipeline (spec.md section 4). No I/O here so these
are unit-testable without a DB or HTTP mocks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CheckResult:
    name: str
    result: str  # PASS, BLOCK, TIGHTEN, SKIPPED
    reason_code: str | None
    source: str
    detail: str | None = None


@dataclass
class PipelineOutcome:
    status: str  # CHECKED, NEEDS_CONFIRMATION, BLOCKED
    checks: list[CheckResult] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def combine_status(checks: list[CheckResult], intent_fit_verdict: str | None) -> str:
    """spec.md section 4 step 9: pure combination rule.

    status = BLOCKED if any hard block/REJECT; NEEDS_CONFIRMATION if verdict != PASS
    (and not None/SKIPPED); else CHECKED. Nothing moves BLOCKED to allowed.
    """
    if any(c.result == "BLOCK" for c in checks):
        return "BLOCKED"
    if intent_fit_verdict == "REJECT_WITH_REASON":
        return "BLOCKED"
    if intent_fit_verdict == "NEEDS_BUYER_CONFIRMATION":
        return "NEEDS_CONFIRMATION"
    return "CHECKED"


def canonical_json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_proposal_hash(
    *,
    mandate_id: str,
    mandate_hash: str,
    lines: list[dict],
    total_minor: int,
    currency: str,
    merchant_ids: list[str],
    policy_version: str | None,
) -> str:
    """spec.md section 4 step 10: SHA-256 of canonical JSON built from validated,
    server-priced data only -- never from client-sent fields.
    """
    sorted_lines = sorted(
        [{"sku": line_["sku"], "qty": line_["qty"]} for line_ in lines],
        key=lambda x: x["sku"],
    )
    obj = {
        "mandate_id": mandate_id,
        "mandate_hash": mandate_hash,
        "lines": sorted_lines,
        "total_minor": total_minor,
        "currency": currency,
        "merchant_ids": sorted(merchant_ids),
        "policy_version": policy_version,
    }
    return sha256_hex(canonical_json_bytes(obj))
