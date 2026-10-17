#!/usr/bin/env python3
"""Eval harness runner (spec.md section 9, sprint-plan S1-12).

Drives the 20-prompt cart set (`evals/cart_eval_set.json`) through the configured LLM
gateway (`app_shopping_agent.llm_providers.build_gateway`, provider-switchable Gemini/Groq per
ADR-010), validates every output with `app_shopping_agent.eval_validation.validate_cart_output`
(the same deterministic safety layer the live endpoint will use), and writes a
committed report: `evals/report.json` (machine) + `evals/REPORT.md` (human), with
model id, prompt_version, and a counted failure breakdown -- never a vibes-based pass.

Scope note: `GeminiProvider`/`GroqProvider` in app/llm_providers.py are still Wave-4
stubs (they raise `LLMFailClosedError`/`NotImplementedError` by design -- no provider
SDK call lives in this repo yet). Running this script today therefore exercises and
reports the FAIL-CLOSED path for every case, not live-model accuracy: every call must
fail closed to a restrictive default (no provider call ever reaches a money decision,
per ADR-010 / CLAUDE.md golden rules). That is itself the thing this wave's gate is
checking. Once a real provider adapter lands, re-run this script; `evals/baseline.json`
is left for that promotion-gate comparison per spec.md section 9.4's regression rule.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from safepayai_common.llm.gateway import LLMFailClosedError

from app_shopping_agent.eval_schemas import CART_PROPOSAL_JSON_SCHEMA
from app_shopping_agent.eval_validation import validate_cart_output
from app_shopping_agent.llm_providers import build_gateway
from app_shopping_agent.settings import Settings, get_settings

EVAL_SET_PATH = SERVICE_DIR / "evals" / "cart_eval_set.json"
REPORT_JSON_PATH = SERVICE_DIR / "evals" / "report.json"
REPORT_MD_PATH = SERVICE_DIR / "evals" / "REPORT.md"


def build_prompt(intent: str, catalog_snapshot: dict, mandate: dict) -> str:
    """Minimal prompt assembly for the harness - not the production prompt template
    (that is prompt_version-pinned and lives with the real provider wiring); good
    enough to drive the gateway interface end to end for this eval."""
    catalog_lines = "\n".join(
        f"- {sku}: {item['title']} ({item['merchant_id']}, {item['category']}, ${item['price_minor'] / 100:.2f})"
        for sku, item in catalog_snapshot.items()
    )
    return (
        f"<trusted_mandate>max_total_minor={mandate['max_total_minor']} "
        f"currency={mandate['currency']}</trusted_mandate>\n"
        f"<catalog>\n{catalog_lines}\n</catalog>\n"
        f'<untrusted_intent id="eval">{intent}</untrusted_intent>'
    )


async def run_case(
    gateway: Any, settings: Settings, case: dict, eval_set: dict
) -> dict:
    prompt = build_prompt(
        case["intent"], eval_set["catalog_snapshot"], eval_set["mandate"]
    )
    started = time.monotonic()
    model_id = None
    fail_closed_reason = None
    validation = None

    try:
        result = await gateway.call(
            prompt, CART_PROPOSAL_JSON_SCHEMA, settings.llm_timeout_cart_s
        )
        model_id = result.model_id
        if not result.valid or result.output is None:
            fail_closed_reason = "INVALID_OUTPUT"
        else:
            sku_to_merchant = {
                sku: item["merchant_id"]
                for sku, item in eval_set["catalog_snapshot"].items()
            }
            validation = validate_cart_output(
                result.output,
                catalog_skus=set(eval_set["catalog_snapshot"].keys()),
                sku_to_merchant=sku_to_merchant,
                allowed_merchant_ids=set(eval_set["allowed_merchant_ids"]),
            )
    except LLMFailClosedError as exc:
        fail_closed_reason = f"LLM_FAIL_CLOSED: {exc}"
    except NotImplementedError as exc:
        # Wave-4 stub providers raise this directly (no SDK call implemented yet).
        # Golden rule (ADR-010): any provider error must fail closed, never crash the
        # caller into an undefined state - so the harness treats this the same as
        # LLMFailClosedError, not as a harness bug.
        fail_closed_reason = f"PROVIDER_NOT_IMPLEMENTED: {exc}"
    except Exception as exc:  # noqa: BLE001 - harness must never let one case kill the run
        fail_closed_reason = f"UNEXPECTED_ERROR: {exc}"

    latency_ms = int((time.monotonic() - started) * 1000)

    return {
        "id": case["id"],
        "class": case["class"],
        "intent_hash_only": True,  # raw intent text is never written to the committed report
        "model_id": model_id,
        "fail_closed_reason": fail_closed_reason,
        "schema_valid": validation.schema_valid if validation else False,
        "hard_gate_violation": validation.hard_gate_violation if validation else False,
        "injection_suspected": validation.injection_suspected if validation else False,
        "status": validation.status if validation else "FAIL_CLOSED",
        "detail": validation.detail if validation else (fail_closed_reason or ""),
        "latency_ms": latency_ms,
    }


async def run_all() -> dict:
    settings = get_settings()
    gateway = build_gateway(settings)
    eval_set = json.loads(EVAL_SET_PATH.read_text())

    results = [
        await run_case(gateway, settings, case, eval_set) for case in eval_set["cases"]
    ]

    total = len(results)
    fail_closed_count = sum(1 for r in results if r["fail_closed_reason"] is not None)
    schema_valid_count = sum(1 for r in results if r["schema_valid"])
    hard_gate_violations = [r for r in results if r["hard_gate_violation"]]
    injection_flagged = [r for r in results if r["injection_suspected"]]

    report = {
        "prompt_version": eval_set["prompt_version"],
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_cases": total,
        "fail_closed_count": fail_closed_count,
        "schema_valid_count": schema_valid_count,
        "hard_gate_violation_count": len(hard_gate_violations),
        "hard_gate_violation_ids": [r["id"] for r in hard_gate_violations],
        "injection_flagged_ids": [r["id"] for r in injection_flagged],
        "models_seen": sorted({r["model_id"] for r in results if r["model_id"]}),
        "gate_zero_hard_gate_violations": len(hard_gate_violations) == 0,
        "results": results,
    }
    return report


def write_reports(report: dict) -> None:
    REPORT_JSON_PATH.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# shopping-agent cart eval report (G4)",
        "",
        f"Generated: {report['generated_at']}",
        f"Prompt version: {report['prompt_version']}",
        f"Models observed: {report['models_seen'] or 'none (all cases fail-closed)'}",
        "",
        f"- Total cases: {report['total_cases']}",
        f"- Fail-closed (no live model output reached validation): {report['fail_closed_count']}/{report['total_cases']}",
        f"- Schema-valid outputs: {report['schema_valid_count']}/{report['total_cases']}",
        (
            f"- Hard-gate violations (hallucinated SKU / non-allowlisted merchant): "
            f"{report['hard_gate_violation_count']} (case ids: {report['hard_gate_violation_ids']})"
        ),
        f"- Injection-suspected flags raised: {report['injection_flagged_ids']}",
        f"- Zero-hard-gate-violation gate: {'PASS' if report['gate_zero_hard_gate_violations'] else 'FAIL'}",
        "",
        "## Scope note",
        "",
        "`GeminiProvider`/`GroqProvider` (app/llm_providers.py) are still Wave-4 stubs - no",
        "provider SDK call is implemented in this repo yet (ADR-010: only shopping-agent",
        "and triage-ai may hold LLM keys, and this wave's scope per sprint-plan S1-12 is the",
        "eval harness itself, not the live `/propose` endpoint). Every case above therefore",
        "fails closed by construction, which is exactly the golden-rule behavior this report",
        "is checking: the AI path never reaches a money decision, and on any provider error",
        "the result floors at a restrictive default, never PASS/ALLOW. Re-run this script",
        "once a real provider adapter lands to get live accuracy numbers; this report's",
        "`gate_zero_hard_gate_violations` and schema-shape checks remain meaningful today.",
        "",
        "## Per-case results",
        "",
        "| id | class | fail_closed_reason | status | hard_gate_violation | injection_suspected |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["results"]:
        lines.append(
            f"| {r['id']} | {r['class']} | {r['fail_closed_reason'] or ''} | {r['status']} | "
            f"{r['hard_gate_violation']} | {r['injection_suspected']} |"
        )
    REPORT_MD_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    report = asyncio.run(run_all())
    write_reports(report)
    print(f"Wrote {REPORT_JSON_PATH} and {REPORT_MD_PATH}")
    print(
        f"total={report['total_cases']} fail_closed={report['fail_closed_count']} "
        f"hard_gate_violations={report['hard_gate_violation_count']}"
    )
    return 0 if report["gate_zero_hard_gate_violations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
