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

from run_agent_eval import run_all


@pytest.mark.asyncio
async def test_every_case_fails_closed_against_stub_providers() -> None:
    report = await run_all()
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
