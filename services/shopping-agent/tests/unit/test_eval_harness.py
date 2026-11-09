"""Tests the eval harness itself fails closed on every case when run against the
current (Wave-4 stub) provider adapters -- this is the behavior sprint-plan S1-12
explicitly asked the harness to test and report, not just happy-path accuracy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICE_DIR / "scripts"))

import run_agent_eval
from run_agent_eval import REPORT_JSON_PATH, REPORT_MD_PATH, run_all

from app_shopping_agent.settings import Settings


@pytest.mark.asyncio
async def test_every_case_fails_closed_against_stub_providers(monkeypatch) -> None:
    # Hermetic: never reach live LLMs even when real keys are in the env / .env, and
    # never touch the committed evals/report.json + REPORT.md (run_all() only returns
    # the report; write_reports() is main()'s job -- guarded below with a snapshot).
    for var in (
        "PS_SHOPPINGAGENT_GEMINI_API_KEY",
        "PS_SHOPPINGAGENT_GROQ_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    ):
        monkeypatch.setenv(var, "")
    monkeypatch.setattr(
        run_agent_eval,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key=None, groq_api_key=None),
    )
    committed = [REPORT_JSON_PATH, REPORT_MD_PATH]
    before = [p.read_bytes() for p in committed]
    report = await run_all()
    assert [p.read_bytes() for p in committed] == before
    assert report["models_seen"] == []
    assert report["total_cases"] == 20
    assert report["fail_closed_count"] == 20
    assert report["hard_gate_violation_count"] == 0
    assert report["gate_zero_hard_gate_violations"] is True
    for r in report["results"]:
        assert r["fail_closed_reason"] is not None
        assert r["status"] != "OK" or r["schema_valid"] is False


def test_eval_set_has_twenty_cases_with_injection_prompts() -> None:
    eval_set = json.loads((SERVICE_DIR / "evals" / "cart_eval_set.json").read_text())
    assert len(eval_set["cases"]) == 20
    classes = {c["class"] for c in eval_set["cases"]}
    assert any(c.startswith("injection") for c in classes)


def test_committed_report_exists_and_matches_schema() -> None:
    report_path = SERVICE_DIR / "evals" / "report.json"
    assert report_path.exists(), "evals/report.json must be committed (G4)"
    report = json.loads(report_path.read_text())
    for key in (
        "prompt_version",
        "generated_at",
        "total_cases",
        "fail_closed_count",
        "hard_gate_violation_count",
        "results",
    ):
        assert key in report
