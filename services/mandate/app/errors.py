"""Mandate error model per api.md section 3: {"error":{"code","message","details"},"request_id"}."""

from __future__ import annotations


class MandateError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, details: dict | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
