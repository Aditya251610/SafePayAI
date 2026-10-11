"""POST /classify, /draft, /brief per triage-ai/api.md sections 1-3.

Wave 4: validated stubs, 501 Not Implemented. Real pipeline (untrusted-text handling,
LLM gateway call via app/llm_provider.py's inert stub, fail-closed routing, regex gate,
reviewer brief) is Wave 5. Caller allowlist (resolution only) is enforced now via deps.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_resolution_caller
from app.schemas.triage import BriefRequest, ClassifyRequest, DraftRequest

router = APIRouter(tags=["triage"])


def _not_implemented(endpoint: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"{endpoint} pending Wave 5")


@router.post("/classify", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def classify(
    body: ClassifyRequest,
    claims: dict = Depends(require_resolution_caller),
) -> None:
    raise _not_implemented("POST /classify")


@router.post("/draft", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def draft(
    body: DraftRequest,
    claims: dict = Depends(require_resolution_caller),
) -> None:
    raise _not_implemented("POST /draft")


@router.post("/brief", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def brief(
    body: BriefRequest,
    claims: dict = Depends(require_resolution_caller),
) -> None:
    raise _not_implemented("POST /brief")
