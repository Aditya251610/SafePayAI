#!/usr/bin/env python3
"""Apply the NON-SECRET settings in deploy/profile-b/render-env.json to the Render hosts.

    python3 scripts/render_apply_env.py            # dry run: show what differs, change nothing
    python3 scripts/render_apply_env.py --apply    # PUT each differing value, then redeploy the hosts

Reads the Render API token structurally from ~/.render/cli.yaml (run `render login` first) and
never prints it or any secret. Only variables listed in render-env.json are touched; keys,
database URLs and tick/HMAC secrets are set separately and are never stored in this repo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.render.com/v1"


def token() -> str:
    cfg = yaml.safe_load(Path(os.path.expanduser("~/.render/cli.yaml")).read_text())
    tok = (cfg.get("api") or {}).get("key") or cfg.get("key")
    if not tok:
        raise SystemExit("no Render token found: run `render login`")
    return tok


def call(tok: str, path: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read() or b"null")


def main() -> None:
    apply = "--apply" in sys.argv
    tok = token()
    plan = {k: v for k, v in json.loads((ROOT / "deploy/profile-b/render-env.json").read_text()).items() if isinstance(v, dict)}
    services = {s["service"]["name"]: s["service"]["id"] for s in call(tok, "/services?limit=100")}
    changed_hosts: list[str] = []
    for name, wanted in plan.items():
        sid = services.get(name)
        if not sid:
            print(f"! {name}: service not found, skipped")
            continue
        current = {d["envVar"]["key"]: d["envVar"].get("value", "") for d in call(tok, f"/services/{sid}/env-vars?limit=100")}
        diff = {k: v for k, v in wanted.items() if current.get(k) != v}
        print(f"{name}: {len(wanted) - len(diff)} up to date, {len(diff)} to set")
        for k in diff:
            print(f"   {'set' if apply else 'would set'} {k}")
            if apply:
                call(tok, f"/services/{sid}/env-vars/{k}", "PUT", {"value": diff[k]})
        if diff and apply:
            changed_hosts.append(sid)
    for sid in changed_hosts:
        subprocess.run(["render", "deploys", "create", sid, "--wait", "--confirm", "-o", "text"], check=False)


if __name__ == "__main__":
    main()
