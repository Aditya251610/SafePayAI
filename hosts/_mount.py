"""Shared helper for Profile B hosts (co-located processes on Render free tier).

Each host file (edge.py, core.py, ai.py, paypal.py) mounts a subset of service FastAPI apps
under their own path prefix into one ASGI app, so only ONE Render web service needs to stay
awake (see architecture/deployment-zero-cost.md §3b). This is deploy glue only — no business
logic. Profile A (docker-compose, one container per service) is the default for local dev and
for judges running the repo; Profile B is only for the hosted demo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.routing import Mount

REPO_ROOT = Path(__file__).resolve().parents[1]


def _package_dir_for(service_dir: Path) -> Path:
    """Each co-mounted service's internal package was renamed from the shared `app` to a
    unique `app_<slug>` (e.g. `app_mandate`, `app_shopping_agent`) specifically to eliminate
    the sys.modules collision this file used to work around with a purge-before-exec hack —
    that hack only fixed eager/module-top imports, not lazy (function-body) ones, and a lazy
    `from app.X import Y` inside a co-mounted service's own code broke in production (found
    live: shopping-agent's form_fallback.py, triage-ai's routers/triage.py, tracking's
    usecases/tick.py + domain/verify.py, resolution's routers/internal.py all had this
    pattern). Services that are never co-mounted with anything else (api-gateway, paypal-
    adapter - each alone on its own Render host) were left as plain `app`, so resolve
    whichever directory actually exists rather than hardcoding either name.
    """
    renamed = service_dir / f"app_{service_dir.name.replace('-', '_')}"
    if renamed.is_dir():
        return renamed
    return service_dir / "app"


def load_service_app(slug: str) -> FastAPI:
    """Imports services/<slug>/<package>/main.py:app under a unique module name per slug."""
    service_dir = REPO_ROOT / "services" / slug
    package_dir = _package_dir_for(service_dir)
    main_py = package_dir / "main.py"
    module_name = f"_safepayai_host_{slug.replace('-', '_')}_main"
    spec = importlib.util.spec_from_file_location(module_name, main_py, submodule_search_locations=[str(package_dir)])
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {main_py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # service code does `from app_<slug>.settings import ...` style relative-to-package
    # imports (or `from app.settings import ...` for the two never-co-mounted services);
    # make the service's own directory importable for the duration of this load.
    sys.path.insert(0, str(service_dir))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(service_dir))
    return getattr(module, "app")


def build_host(prefix_to_slug: dict[str, str]) -> Starlette:
    routes = [Mount(prefix, app=load_service_app(slug)) for prefix, slug in prefix_to_slug.items()]
    return Starlette(routes=routes)


# FIXED, properly this time (was: "KNOWN LIMITATION, do not ship Profile B on this until
# fixed", then a sys.modules-purge workaround that only covered eager/module-top imports).
# A purge-before-exec approach left `sys.modules["app"]` pointing at whichever service loaded
# LAST for the rest of the process's lifetime, so any LAZY `from app.X import Y` written
# inside a function body (not at module top) - executed later, during a real request, not at
# startup - resolved against the wrong service's package. This broke in production: shopping-
# agent's form_fallback.py crashed with `ModuleNotFoundError: No module named
# 'app.catalog_filter'` because triage-ai (mounted after it) had overwritten `sys.modules
# ["app"]` by request time. The real fix is the one this module's docstring originally named
# as the alternative: each co-mounted service's internal package is now uniquely named
# (`app_mandate`, `app_catalog`, `app_checkout`, `app_tracking`, `app_resolution`, `app_audit`,
# `app_shopping_agent`, `app_triage_ai`), eliminating the shared-namespace problem at the root
# instead of patching around it. `_package_dir_for` resolves whichever directory actually
# exists per service, since api-gateway/paypal-adapter were left as plain `app` (never
# co-mounted with anything, so no collision risk). Profile A (docker-compose, one process per
# service) never had this issue either way and remains the default for local/dev and for
# judges running the repo from a clean checkout.
