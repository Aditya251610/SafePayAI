# Profile A (fully separated services, local dev)

Profile A is the root-level `docker-compose.yml` — one container per service, matching
`architecture/adr.md` ADR-009 and `architecture/deployment-zero-cost.md` §3b. This directory holds
Profile-A-specific overrides only (e.g. a `docker-compose.override.yml` for a judge's local run)
if/when one is needed; there is none yet. Run with:

```bash
cp .env.example .env
docker compose up
```
