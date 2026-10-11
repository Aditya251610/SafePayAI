"""Hand-written JSON-RPC MCP stub at POST /mcp (streamable HTTP), ADR-007.

Wave 4: wires auth + the per-caller tool allowlist (api.md section 8) so `tools/list` is
filtered and a `tools/call` always returns `isError=true` with `NOT_PERMITTED` or
`not_implemented` -- no PayPal call, no ticket verification logic yet (Wave 5). Not mounted
behind api-gateway (spec.md section 1); reached only via direct HTTP to this process.

U11 (spec.md section 4.2): MCP Python SDK mount API unverified; this hand-written handler is
the documented fallback, not a placeholder we intend to delete silently.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.deps import DEFAULT_ALLOWLIST
from app.settings import get_settings

router = APIRouter(tags=["mcp"])

ALL_TOOLS = list(DEFAULT_ALLOWLIST.keys())


def _tools_for_caller(caller_sub: str | None) -> list[str]:
    if not caller_sub:
        return []
    return [tool for tool, allowed in DEFAULT_ALLOWLIST.items() if caller_sub in allowed]


def _extract_caller(request: Request) -> str | None:
    settings = get_settings()
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or not settings.internal_jwks_url:
        return None
    token = auth.removeprefix("Bearer ").strip()
    try:
        jwks_client = jwt.PyJWKClient(settings.internal_jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256", "EdDSA"], audience=settings.internal_jwt_aud
        )
        return claims.get("sub")
    except jwt.PyJWTError:
        return None


@router.post("/mcp")
async def mcp_jsonrpc(request: Request) -> JSONResponse:
    body = await request.json()
    rpc_id = body.get("id")
    method = body.get("method")
    caller_sub = _extract_caller(request)

    if caller_sub is None:
        return JSONResponse(status_code=401, content={"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32001, "message": "UNAUTHENTICATED"}})

    if method == "tools/list":
        tools = _tools_for_caller(caller_sub)
        return JSONResponse(
            content={"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": [{"name": t} for t in tools]}}
        )

    if method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        allowed = DEFAULT_ALLOWLIST.get(name, set())
        if name not in ALL_TOOLS or caller_sub not in allowed:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "isError": True,
                        "structuredContent": {
                            "ok": False,
                            "status": "REJECTED",
                            "paypal_http_status": None,
                            "data": None,
                            "error": {"code": "NOT_PERMITTED", "message": "not permitted", "retryable": False, "paypal_name": None},
                            "replayed": False,
                            "trace_id": str(uuid.uuid4()),
                        },
                        "content": [{"type": "text", "text": "Not permitted."}],
                    },
                }
            )
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "isError": True,
                    "structuredContent": {
                        "ok": False,
                        "status": "REJECTED",
                        "paypal_http_status": None,
                        "data": None,
                        "error": {"code": "not_implemented", "message": f"{name} pending Wave 5", "retryable": False, "paypal_name": None},
                        "replayed": False,
                        "trace_id": str(uuid.uuid4()),
                    },
                    "content": [{"type": "text", "text": f"{name} not implemented (Wave 4 stub)."}],
                },
            }
        )

    return JSONResponse(
        status_code=400,
        content={"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": "method not found"}},
    )
