"""POST /prices/resolve - stub per catalog/api.md and spec.md section 5.

Request validation uses the real pydantic schema from the OpenAPI contract
(app/schemas/prices.py); the pricing algorithm itself is Wave 5 business logic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import Principal, verify_internal_jwt
from app.schemas.prices import PriceResolveRequest

router = APIRouter(tags=["prices"])


@router.post("/prices/resolve")
async def resolve_prices(
    body: PriceResolveRequest, response: Response, principal: Principal = Depends(verify_internal_jwt)
) -> dict:
    response.status_code = 501
    return {"error": "not_implemented", "detail": "POST /prices/resolve pending Wave 5"}
