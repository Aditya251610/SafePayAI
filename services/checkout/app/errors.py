"""Business error type for checkout, mirroring catalog/app/errors.py's envelope decision.

{"error": "<CODE>", "detail": "<human string>", "request_id": "<uuid or null>", "details": {}}
"""

from __future__ import annotations


class CheckoutError(Exception):
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
