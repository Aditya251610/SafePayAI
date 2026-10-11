# Build context MUST be the repo root (see docker-compose.yml build.context and
# .github/workflows/ci-python-service.yml), not this directory: this service depends on the
# shared `libs/common` workspace package, and uv needs every workspace member's pyproject.toml
# present (even ones it won't install) to resolve the lockfile.
FROM python:3.12-slim AS base
WORKDIR /workspace
RUN pip install --no-cache-dir uv
COPY . .
RUN uv sync --frozen --no-dev --package ps-resolution
WORKDIR /workspace/services/resolution
EXPOSE 8000
CMD ["uv", "run", "--project", "/workspace", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
