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


def load_service_app(slug: str) -> FastAPI:
    """Imports services/<slug>/app/main.py:app under a unique module name per slug, so that
    mounting two services both named `app.main` in one process never collides in sys.modules."""
    service_dir = REPO_ROOT / "services" / slug
    main_py = service_dir / "app" / "main.py"
    module_name = f"_safepayai_host_{slug.replace('-', '_')}_main"
    spec = importlib.util.spec_from_file_location(module_name, main_py, submodule_search_locations=[str(service_dir / "app")])
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {main_py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # service code does `from app.settings import ...` style relative-to-package imports;
    # make the service's own directory importable as top-level `app` for the duration of this load.
    sys.path.insert(0, str(service_dir))
    # Every service's internal package is named `app` (docs/service-skeleton-conventions.md).
    # A previously-loaded service left its own `app`/`app.*` modules cached in sys.modules, and
    # Python's import system resolves `from app.settings import ...` against that cache, not
    # against the directory now on sys.path — the collision _mount.py's module docstring above
    # used to warn about. Evict the whole `app` namespace right before exec so this service's
    # own main.py always gets a fresh, correctly-scoped `app` package. Safe because each
    # service's main.py only has module-level side effects on itself (FastAPI() construction,
    # router includes, a `get_settings()` fail-fast call) — nothing registers into shared global
    # state that a fresh re-import would lose.
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(service_dir))
    return getattr(module, "app")


def build_host(prefix_to_slug: dict[str, str]) -> Starlette:
    routes = [Mount(prefix, app=load_service_app(slug)) for prefix, slug in prefix_to_slug.items()]
    return Starlette(routes=routes)


# FIXED (was: "KNOWN LIMITATION, do not ship Profile B on this until fixed"). Every service's
# internal package is named `app` (per docs/service-skeleton-conventions.md), so loading two
# services' main.py in one process both doing `from app.settings import Settings` used to have
# the second service's imports resolve against the FIRST service's already-cached top-level
# `app` package, not its own. `load_service_app` above now evicts `app`/`app.*` from
# sys.modules immediately before each service's main.py execs, so every service always sees its
# own fresh `app` package — verified safe because no service's main.py has side effects beyond
# its own FastAPI()/router/settings construction (see each main.py's module-level code). Profile
# A (docker-compose, one process per service) never had this issue and remains the default for
# local/dev and for judges running the repo from a clean checkout.
