"""Use-case layer for resolution: transactions, row locks, outbox writes. Calls app/domain/ for rules.

Named `usecases` (not `app/` as in spec s1) because `app` is already the FastAPI package.
"""
