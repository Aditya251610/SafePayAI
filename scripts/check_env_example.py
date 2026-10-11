#!/usr/bin/env python3
"""CI check: every PS_<SLUG>_* / documented-exception env var referenced in a service's app code
must appear in that service's own .env.example. Catches "works on my machine" env drift before
it reaches CI/deploy. See architecture/ci-cd-and-repo-workflow.md §9.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_VAR_PATTERN = re.compile(r"\b(PS_[A-Z0-9_]+|PAYPAL_[A-Z0-9_]+|MANDATE_HMAC_KEY[A-Z_]*|INTERNAL_TICK_SECRET)\b")


def vars_in_code(service_dir: Path) -> set[str]:
    found: set[str] = set()
    for py_file in (service_dir / "app").rglob("*.py"):
        found |= set(ENV_VAR_PATTERN.findall(py_file.read_text(errors="ignore")))
    return found


def vars_in_env_example(service_dir: Path) -> set[str]:
    env_example = service_dir / ".env.example"
    if not env_example.exists():
        return set()
    names = set()
    for line in env_example.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        names.add(line.split("=", 1)[0].strip())
    return names


def main() -> int:
    services_dir = REPO_ROOT / "services"
    failed = False
    for service_dir in sorted(p for p in services_dir.iterdir() if p.is_dir() and p.name != "web"):
        code_vars = vars_in_code(service_dir)
        example_vars = vars_in_env_example(service_dir)
        missing = code_vars - example_vars
        if missing:
            failed = True
            print(f"{service_dir.name}: vars used in code but missing from .env.example: {sorted(missing)}")
    if failed:
        return 1
    print("check_env_example: all referenced vars are documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
