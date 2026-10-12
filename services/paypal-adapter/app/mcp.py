"""Hand-written JSON-RPC MCP server at POST /mcp (streamable HTTP), ADR-007.

U11 (spec.md section 4.2): the Python MCP SDK's FastMCP mount API is unverified in this repo
(no `mcp`/`fastmcp` dependency declared in pyproject.toml yet) -- this hand-written handler is
the documented fallback the Wave 4 docstring called out, not a placeholder; keeping it avoids
burning time pinning down an unverified SDK mount for a hackathon deadline. Not mounted behind
api-gateway (spec.md section 1); reached only via direct HTTP to this process.

Tools call the exact same `app.ops` functions as the REST routers (one code path for money,
per agent-and-mcp-design.md section 1 "MCP tools call the same internal functions"). Wired:
create_order, get_order, capture_order, refund_capture, get_refund. `add_tracking` stays
`not_implemented` -- its own REST endpoint (app/routers/tracking.py) is still a Wave 4 stub,
out of this task's scope (no app.ops.add_tracking to call).

Per-tool caller allowlist (api.md section 8, app.deps.DEFAULT_ALLOWLIST) is enforced before
dispatch for every tool, independent of the code wiring here: resolution-only for
refund_capture/get_refund, LLM-holding services (shopping-agent, triage-ai) are denied on
every tool because they are not in any tool's allowlist entry (see
tests/unit/test_mcp_allowlist.py).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import ops
from app.db import get_session_factory
from app.deps import DEFAULT_ALLOWLIST, verify_internal_jwt
from app.ops import OpError
from app.paypal_client import get_paypal_client_for
from app.settings import get_settings

router = APIRouter(tags=["mcp"])

ALL_TOOLS = list(DEFAULT_ALLOWLIST.keys())
WIRED_TOOLS = {"create_order", "get_order", "capture_order", "refund_capture", "get_refund"}


def _tools_for_caller(caller_sub: str | None) -> list[str]:
    if not caller_sub:
        return []
    return [tool for tool, allowed in DEFAULT_ALLOWLIST.items() if caller_sub in allowed]


def _extract_caller(request: Request) -> str | None:
    settings = get_settings()
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    try:
        claims = verify_internal_jwt(token, settings)
    except Exception:  # noqa: BLE001 - _AuthUnavailable is a private deps.py signal
        return None
    return claims.get("sub") if claims else None


def _error_result(rpc_id: Any, code: str, message: str) -> JSONResponse:
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
                    "error": {
                        "code": code,
                        "message": message,
                        "retryable": False,
                        "paypal_name": None,
                    },
                    "replayed": False,
                    "trace_id": str(uuid.uuid4()),
                },
                "content": [{"type": "text", "text": message}],
            },
        }
    )


def _ok_result(rpc_id: Any, envelope: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "isError": not envelope.get("ok", False),
                "structuredContent": envelope,
                "content": [{"type": "text", "text": envelope.get("status", "")}],
            },
        }
    )


def _missing(args: dict[str, Any], *names: str) -> str | None:
    for name in names:
        if args.get(name) in (None, ""):
            return name
    return None


async def _dispatch_tool(name: str, caller_sub: str, args: dict[str, Any]) -> dict[str, Any]:
    """Calls the exact same app.ops function the REST routers call. Raises ops.OpError on
    any rejection/ambiguity; callers of this function translate that into the MCP error
    shape, same envelope as REST (api.md section 2)."""
    trace_id = str(uuid.uuid4())
    settings = get_settings()
    client = get_paypal_client_for(settings)

    if name == "get_order":
        missing = _missing(args, "order_id")
        if missing:
            raise OpError("REJECTED", "VALIDATION_ERROR", f"missing {missing}", http_status=422)
        return await ops.get_order(client, args["order_id"], trace_id=trace_id)

    if name == "get_refund":
        missing = _missing(args, "refund_id")
        if missing:
            raise OpError("REJECTED", "VALIDATION_ERROR", f"missing {missing}", http_status=422)
        async with get_session_factory()() as session:
            return await ops.get_refund(session, client, args["refund_id"], trace_id=trace_id)

    if name == "create_order":
        required = (
            "request_id",
            "mandate_id",
            "internal_order_id",
            "amount_minor",
            "currency",
            "return_url",
            "cancel_url",
        )
        missing = _missing(args, *required)
        if missing:
            raise OpError("REJECTED", "VALIDATION_ERROR", f"missing {missing}", http_status=422)
        async with get_session_factory()() as session:
            return await ops.create_order(
                session,
                client,
                settings,
                caller=caller_sub,
                request_id=args["request_id"],
                mandate_id=args["mandate_id"],
                internal_order_id=args["internal_order_id"],
                amount_minor=int(args["amount_minor"]),
                currency=args["currency"],
                return_url=args["return_url"],
                cancel_url=args["cancel_url"],
                trace_id=trace_id,
            )

    if name == "capture_order":
        missing = _missing(args, "order_id", "request_id", "mandate_id", "amount_minor", "currency")
        if missing:
            raise OpError("REJECTED", "VALIDATION_ERROR", f"missing {missing}", http_status=422)
        async with get_session_factory()() as session:
            return await ops.capture_order(
                session,
                client,
                settings,
                caller=caller_sub,
                order_id=args["order_id"],
                request_id=args["request_id"],
                mandate_id=args["mandate_id"],
                amount_minor=int(args["amount_minor"]),
                currency=args["currency"],
                trace_id=trace_id,
            )

    if name == "refund_capture":
        missing = _missing(args, "capture_id", "request_id", "amount_minor", "currency", "ticket")
        if missing:
            raise OpError("REJECTED", "VALIDATION_ERROR", f"missing {missing}", http_status=422)
        async with get_session_factory()() as session:
            return await ops.refund_capture(
                session,
                client,
                settings,
                caller=caller_sub,
                capture_id=args["capture_id"],
                request_id=args["request_id"],
                invoice_id=args.get("invoice_id"),
                amount_minor=int(args["amount_minor"]),
                currency=args["currency"],
                ticket=args["ticket"],
                trace_id=trace_id,
            )

    raise OpError("REJECTED", "not_implemented", f"{name} pending Wave 5", http_status=501)


@router.post("/mcp")
async def mcp_jsonrpc(request: Request) -> JSONResponse:
    body = await request.json()
    rpc_id = body.get("id")
    method = body.get("method")
    caller_sub = _extract_caller(request)

    if caller_sub is None:
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32001, "message": "UNAUTHENTICATED"},
            },
        )

    if method == "tools/list":
        tools = _tools_for_caller(caller_sub)
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"tools": [{"name": t} for t in tools]},
            }
        )

    if method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        allowed = DEFAULT_ALLOWLIST.get(name, set())
        if name not in ALL_TOOLS or caller_sub not in allowed:
            return _error_result(rpc_id, "NOT_PERMITTED", "not permitted")

        if name not in WIRED_TOOLS:
            return _error_result(rpc_id, "not_implemented", f"{name} pending Wave 5")

        try:
            envelope = await _dispatch_tool(name, caller_sub, args)
        except OpError as exc:
            return _error_result(rpc_id, exc.code, exc.message)
        return _ok_result(rpc_id, envelope)

    return JSONResponse(
        status_code=400,
        content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": "method not found"},
        },
    )
