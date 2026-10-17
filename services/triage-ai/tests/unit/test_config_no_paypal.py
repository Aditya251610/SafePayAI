"""ADR-010 config test: triage-ai must hold no PayPal credentials and have no code path
that can reach paypal-adapter or any money service's HTTP client (build-spec section 8 /
spec.md section 1: "package app/ must not import any money-service client"). This is the
one golden-rule check the build spec explicitly requires extending if any new settings
field is added - run it on every change to app/settings.py or any new outbound call site.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app_triage_ai.settings import Settings

pytestmark = pytest.mark.unit

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app_triage_ai"

_FORBIDDEN_MONEY_IMPORT_SUBSTRINGS = (
    "paypal",
    "checkout",
    "mandate",
    "resolution_client",
)


def test_settings_has_no_paypal_credential_fields() -> None:
    field_names = set(Settings.model_fields.keys())
    for name in field_names:
        assert "paypal" not in name.lower(), f"unexpected PayPal-shaped field: {name}"


def test_env_prefix_is_triageai() -> None:
    assert Settings.model_config.get("env_prefix") == "PS_TRIAGEAI_"


def _iter_python_files():
    return sorted(p for p in APP_DIR.rglob("*.py"))


def test_no_money_service_client_imports_anywhere_in_app() -> None:
    """Static check: no module under app/ imports anything that looks like a PayPal/
    checkout/mandate/resolution HTTP client. triage-ai's own settings legitimately read a
    `resolution`-shaped caller allowlist string (not a client import), which this check
    does not touch - it only inspects `import`/`from ... import` statements."""
    violations: list[str] = []
    for path in _iter_python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                lowered = name.lower()
                if any(bad in lowered for bad in _FORBIDDEN_MONEY_IMPORT_SUBSTRINGS):
                    violations.append(
                        f"{path.relative_to(APP_DIR.parent)}: import {name}"
                    )
    assert violations == [], f"forbidden money-service imports found: {violations}"


def test_no_outbound_http_base_urls_point_at_other_services() -> None:
    """triage-ai's only outbound network call is to the configured LLM provider
    (Gemini/Groq) - grep app/ for any hardcoded internal service URL/hostname."""
    forbidden_hosts = ("paypal-adapter", "checkout:", "mandate:", "resolution:")
    violations: list[str] = []
    for path in _iter_python_files():
        text = path.read_text()
        for host in forbidden_hosts:
            if host in text:
                violations.append(f"{path.name}: references {host!r}")
    assert violations == [], f"forbidden outbound host references: {violations}"
