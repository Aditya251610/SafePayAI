# Build context MUST be the repo root (see docker-compose.yml build.context and
# .github/workflows/ci-python-service.yml), not this directory: this service depends on the
# shared `libs/common` workspace package, and uv needs every workspace member's pyproject.toml
# present (even ones it won't install) to resolve the lockfile.
FROM python:3.12-slim AS base
WORKDIR /workspace
RUN pip install --no-cache-dir uv
COPY . .
RUN uv sync --frozen --no-dev --package ps-triage-ai
RUN addgroup --system app && adduser --system --ingroup app app && chown -R app:app /workspace
ENV UV_CACHE_DIR=/workspace/.cache/uv HOME=/workspace
USER app
WORKDIR /workspace/services/triage-ai
EXPOSE 8000
CMD ["uv", "run", "--project", "/workspace", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
