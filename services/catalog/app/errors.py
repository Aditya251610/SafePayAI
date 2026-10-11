"""Business error type for catalog, carrying the error codes catalog/spec.md section 9
defines (UNKNOWN_SKU, ITEM_INACTIVE, ...).

Deliberate envelope decision (flagged for the catalog owner): docs/service-skeleton-
conventions.md section 4 pins the generic envelope to exactly
{"error": "<snake_case>", "detail": "<human string>", "request_id": "<uuid or null>"}.
catalog/spec.md section 9 and api.md's error example additionally require a machine
`code` (e.g. "UNKNOWN_SKU") and a structured `details` object (e.g. {"skus": [...]})
that callers (checkout, shopping-agent) parse programmatically. There is no documented
third option that satisfies both verbatim. Resolution used here: keep the conventions
doc's three top-level keys, put catalog's documented error `code` in the `error` field
(instead of a generic snake_case slug), and ADD a `details` key alongside - additive,
not a conflicting rename of any key the conventions doc defines. app/main.py's
exception handler is the single place this shape is produced.
"""

from __future__ import annotations


class CatalogError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
