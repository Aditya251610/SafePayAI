"""Auth endpoint schemas, mirrors api-gateway/api.md section 3."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handle: str
    password: str


class DemoPersonaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handle: str


HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")
# Handles that collide with seeded/staff identities or demo personas.
RESERVED_HANDLE_PREFIXES = (
    "merchant-",
    "operator",
    "reviewer",
    "admin",
    "demo",
    "buyer-persona",
)


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handle: str
    password: str = Field(min_length=10, max_length=128, repr=False)
    display_name: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("handle", mode="before")
    @classmethod
    def _normalise_handle(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("handle")
    @classmethod
    def _check_handle(cls, v: str) -> str:
        if not HANDLE_RE.fullmatch(v):
            raise ValueError("handle must match ^[a-z0-9][a-z0-9_-]{2,31}$")
        if v.startswith(RESERVED_HANDLE_PREFIXES):
            raise ValueError("handle is reserved")
        return v


class Principal(BaseModel):
    actor_type: str
    actor_id: str
    role: str
    display_name: str | None = None


class SessionResponse(BaseModel):
    principal: Principal
    expires_at: str


class MeResponse(BaseModel):
    actor_type: str
    actor_id: str
    role: str
    auth_method: str
    display_name: str | None = None
    session_expires_at: str


class CsrfResponse(BaseModel):
    csrf_token: str
    purpose: str
    expires_at: str
