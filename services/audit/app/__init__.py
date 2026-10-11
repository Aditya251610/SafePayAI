"""SafePayAI audit service application package.

Append-only, hash-chained event log. Not on the money path, never decides anything
(.claude/prd/services/audit/prd.md sec 1). Wave 4: contracts + skeleton only — every
route except /healthz and /readyz is a 501 stub (service-skeleton-conventions.md sec 1).
"""
