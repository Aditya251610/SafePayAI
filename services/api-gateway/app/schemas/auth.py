"""Auth endpoint schemas, mirrors api-gateway/api.md section 3."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handle: str
    password: str


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
