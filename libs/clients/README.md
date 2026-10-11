# libs/clients

Generated HTTP client stubs (one per service, from `contracts/openapi/<slug>.yaml`), used by
services that call other services synchronously (e.g. `checkout` -> `mandate`, `tracking` ->
`resolution`). Generation command and the generated output land here starting Wave 5, once the
OpenAPI contracts are implemented against (not just declared). No business logic — generated code
plus a thin typed wrapper only.
