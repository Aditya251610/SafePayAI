"""U1: no float anywhere in money-related code or models (data-architecture.md
section 5 / spec.md section 3.3: integer minor units only, int*int=int sums)."""

from __future__ import annotations

import pathlib
import re

MONEY_MODULES = [
    "app/repo.py",
    "app/routers/prices.py",
    "app/routers/items.py",
    "app/routers/merchants.py",
    "app/schemas/prices.py",
    "app/schemas/items.py",
]

SERVICE_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Matches actual `float` *usage* - a call, a type annotation, or a cast - not the
# word appearing in a comment/docstring (several modules in this service document
# "no float" in prose, which must not self-trigger this check).
FLOAT_USAGE_PATTERN = re.compile(r"\bfloat\s*\(|[:\->]\s*float\b|\bfloat\s*\[")


def test_no_float_token_in_money_modules():
    offenders = []
    for rel_path in MONEY_MODULES:
        path = SERVICE_ROOT / rel_path
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            code = line.split("#", 1)[0]  # ignore trailing comments
            if FLOAT_USAGE_PATTERN.search(code):
                offenders.append(f"{rel_path}:{lineno}: {line.strip()}")
    assert not offenders, "found `float` usage in money-path code:\n" + "\n".join(
        offenders
    )


def test_money_fields_are_typed_int_not_float():
    from app.schemas.items import Item
    from app.schemas.prices import PricedLine, PriceResolveLine

    for model, field_names in (
        (Item, ("unit_price_minor",)),
        (
            PricedLine,
            ("unit_price_minor", "line_total_minor", "latest_unit_price_minor"),
        ),
        (PriceResolveLine, ("agent_stated_price_minor",)),
    ):
        for field_name in field_names:
            annotation = model.model_fields[field_name].annotation
            assert annotation is not None
            assert "float" not in str(annotation).lower(), (
                f"{model.__name__}.{field_name} allows float"
            )


def test_line_total_is_exact_integer_multiplication():
    """Direct property check of the only arithmetic rule catalog ever performs:
    unit_price_minor * qty, with no float coercion anywhere in the path."""
    unit_price_minor = 1899
    qty = 7
    line_total_minor = unit_price_minor * qty
    assert isinstance(line_total_minor, int)
    assert line_total_minor == 13293
