"""GET /.well-known/jwks.json - stub per spec.md section 5.1 / api.md section 3.

Per this agent's instructions: api-gateway's session/cookie and JWKS-serving
endpoints are modeled per its own spec but remain Wave-4 stubs (501) like every
other non-health route; wiring the real public-key set is Wave 5.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json")
async def jwks(response: Response) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "GET /.well-known/jwks.json pending Wave 5"}
