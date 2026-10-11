"""Profile B host: ai. The only two services holding LLM keys (ADR-010 isolation).
See _mount.py for caveats."""

from hosts._mount import build_host

app = build_host({"/shopping-agent": "shopping-agent", "/triage-ai": "triage-ai"})
