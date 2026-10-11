"""GET /.well-known/jwks.json - real implementation (spec.md section 2 / 7 / 15)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.settings import Settings, get_settings
from app.tokens.keys import build_jwks_document

router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json")
async def jwks(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    response.headers["Cache-Control"] = "public, max-age=300"
    return build_jwks_document(settings)
