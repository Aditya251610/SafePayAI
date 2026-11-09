# Product images

- One flat SVG per catalog SKU (`<sku>.svg`) plus `placeholder.svg`, all generated.
- Do not hand-edit. Regenerate with `python3 scripts/generate_product_images.py`.
- Source: `services/catalog/app_catalog/seed/catalog_seed.json` (`art` glyph key, falls back to the category).
- Variation (secondary accent, tilt, corner decoration) is derived from a SHA-256 of the SKU, so output is deterministic.
- `--out DIR` changes the target; `--check` verifies every SKU has a file that parses.
- These are illustrations, not photos of real products.
