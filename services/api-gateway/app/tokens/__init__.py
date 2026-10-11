"""Internal JWT minting + key/JWKS loading (spec.md section 7). api-gateway is the
one service that mints; every other service only verifies via JWKS or a static
`trusted_issuers` fallback (spec.md C1)."""
