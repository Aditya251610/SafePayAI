"""Profile B host: core. Mandate, catalog, checkout, tracking, resolution, audit — no LLM keys,
no PayPal creds. See _mount.py for caveats."""

from hosts._mount import build_host

app = build_host(
    {
        "/mandate": "mandate",
        "/catalog": "catalog",
        "/checkout": "checkout",
        "/tracking": "tracking",
        "/resolution": "resolution",
        "/audit": "audit",
    }
)
