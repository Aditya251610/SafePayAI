"""Fail-fast check for committed .env.example placeholder secrets leaking into a real run.

Every service's .env.example documents its secret fields with a value starting with
"changeme" (see root .env.example and each services/<slug>/.env.example). CI never sets
these env vars to that literal value, so this check is safe to run unconditionally at
settings-construction time without breaking tests.
"""

from __future__ import annotations

_PLACEHOLDER_PREFIX = "changeme"


def assert_no_placeholder_secrets(secrets: dict[str, str | None]) -> None:
    """Raise RuntimeError if any named secret still holds its .env.example placeholder.

    `secrets` maps the env var name (for the error message) to its configured value.
    None/empty values are not checked here -- that's a separate "missing secret"
    concern this guard doesn't own.
    """
    offending = sorted(
        name
        for name, value in secrets.items()
        if value is not None and value.strip().lower().startswith(_PLACEHOLDER_PREFIX)
    )
    if offending:
        raise RuntimeError(
            "Refusing to start: placeholder secret(s) from .env.example still set: "
            f"{', '.join(offending)}. Replace with a real generated value."
        )
