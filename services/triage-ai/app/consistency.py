"""Deterministic text-vs-timeline consistency rules (spec.md section 8.2). These rules are
AUTHORITATIVE (not the model) and run BEFORE any LLM call - each has a unit test. Flags are
phrased neutrally ("buyer text says X; timeline shows Y"), never "buyer lied" - AI/rules
never deny a claim, only surface it for a human (threat-model: AI never decides money).

Scope note: implements CLAIM_NOT_RECEIVED_BUT_DELIVERED, CLAIM_LATE_BUT_ON_TIME,
CLAIM_LOST_BUT_IN_TRANSIT_RECENT, CLAIM_DAMAGED_BUT_NOT_DELIVERED,
CLAIM_WRONG_ITEM_BUT_NOT_DELIVERED, and NOTE_CONTAINS_INSTRUCTION from spec.md's 9-code
table. CLAIM_DELIVERED_DATE_MISMATCH (best-effort date-in-prose parsing) and
TEXT_CATEGORY_VS_DETECTOR_KIND (no `detector_kind` field on the current request schema) are
deferred - flagged, not silently dropped.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Protocol

from app.gate import check_gate
from app.schemas.triage import ShipStatus

_NOT_RECEIVED_PHRASES = (
    "never arrived",
    "not received",
    "didn't receive",
    "did not receive",
    "still waiting",
    "haven't received",
    "have not received",
)
_LATE_PHRASES = (
    "late",
    "delayed",
    "still hasn't arrived",
    "taking too long",
    "took too long",
)
_LOST_PHRASES = ("lost", "missing")
_DAMAGED_PHRASES = ("damaged", "broken", "crushed", "shattered", "cracked")
_WRONG_ITEM_PHRASES = (
    "wrong item",
    "not as described",
    "different item",
    "incorrect item",
)


class _TimelineEventLike(Protocol):
    event_id: str
    ts: datetime
    status: ShipStatus
    note: str | None


def _mentions_any(text: str, phrases: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(p in lowered for p in phrases)


def compute_timeline_flags(
    *,
    buyer_text: str,
    timeline: Sequence[_TimelineEventLike],
    promised_by: date | None,
    demo_now: datetime,
    stale_window_hours: int,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    text = (buyer_text or "").strip()

    delivered_events = [e for e in timeline if e.status == "DELIVERED"]
    in_transit_events = [
        e for e in timeline if e.status in ("IN_TRANSIT", "SHIPPED", "LABEL_CREATED")
    ]

    if text and delivered_events:
        delivered_ts = min(e.ts for e in delivered_events)
        delivered_ids = [e.event_id for e in delivered_events]

        if _mentions_any(text, _NOT_RECEIVED_PHRASES) or _mentions_any(
            text, _LOST_PHRASES
        ):
            flags.append(
                {
                    "code": "CLAIM_NOT_RECEIVED_BUT_DELIVERED",
                    "severity": "WARN",
                    "origin": "rule",
                    "event_ids": delivered_ids[:5],
                    "explanation": (
                        f"Buyer text says not received/lost; timeline shows DELIVERED at "
                        f"{delivered_ts.isoformat()}."
                    ),
                }
            )

        if (
            _mentions_any(text, _LATE_PHRASES)
            and promised_by is not None
            and delivered_ts.date() <= promised_by
        ):
            flags.append(
                {
                    "code": "CLAIM_LATE_BUT_ON_TIME",
                    "severity": "WARN",
                    "origin": "rule",
                    "event_ids": delivered_ids[:5],
                    "explanation": (
                        f"Buyer text says late; timeline shows DELIVERED by promised_by "
                        f"({promised_by.isoformat()})."
                    ),
                }
            )

    if text and not delivered_events:
        if _mentions_any(text, _DAMAGED_PHRASES):
            flags.append(
                {
                    "code": "CLAIM_DAMAGED_BUT_NOT_DELIVERED",
                    "severity": "WARN",
                    "origin": "rule",
                    "event_ids": [e.event_id for e in timeline[-3:]],
                    "explanation": "Buyer text says damaged; timeline has no DELIVERED event.",
                }
            )
        if _mentions_any(text, _WRONG_ITEM_PHRASES):
            flags.append(
                {
                    "code": "CLAIM_WRONG_ITEM_BUT_NOT_DELIVERED",
                    "severity": "WARN",
                    "origin": "rule",
                    "event_ids": [e.event_id for e in timeline[-3:]],
                    "explanation": (
                        "Buyer text says wrong item/not as described; timeline has no "
                        "DELIVERED event."
                    ),
                }
            )
        if _mentions_any(text, _LOST_PHRASES) and in_transit_events:
            last_event = max(in_transit_events, key=lambda e: e.ts)
            age_hours = (demo_now - last_event.ts).total_seconds() / 3600
            if age_hours < stale_window_hours:
                flags.append(
                    {
                        "code": "CLAIM_LOST_BUT_IN_TRANSIT_RECENT",
                        "severity": "INFO",
                        "origin": "rule",
                        "event_ids": [last_event.event_id],
                        "explanation": (
                            f"Buyer text says lost; last status {last_event.status} is only "
                            f"{age_hours:.0f}h old (stale window {stale_window_hours}h)."
                        ),
                    }
                )

    for event in timeline:
        if event.note and "G-INSTR" in check_gate(event.note):
            flags.append(
                {
                    "code": "NOTE_CONTAINS_INSTRUCTION",
                    "severity": "WARN",
                    "origin": "rule",
                    "event_ids": [event.event_id],
                    "explanation": (
                        "Carrier note contains instruction-like language; treated as data "
                        "only, never followed."
                    ),
                }
            )

    return flags


__all__ = ["compute_timeline_flags"]
