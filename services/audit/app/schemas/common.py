"""Shapes shared across routers."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Error envelope per service-skeleton-conventions.md sec 4.

    Deviation note: audit's own api.md sec 0 documents a different field name
    (`{"error","message","request_id"}`, citing auth-gateway.md sec 2) instead of
    `detail`. service-skeleton-conventions.md sec 4 explicitly specifies the
    `{"error","detail","request_id"}` shape for "every non-2xx JSON response" across all
    11 services, so the conventions doc wins here (it is not marked service-specific);
    flagged for the gateway/audit doc owners to reconcile api.md's wording with the
    platform-wide envelope.
    """

    error: str
    detail: str
    request_id: str | None = None
