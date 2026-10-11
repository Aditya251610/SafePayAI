# contracts/events

Event JSON Schemas (one file per event type, `schemas/<event_type>.json`), generated from each
service's event catalog in `architecture/overview.md` / `architecture/service-map.md`. Consumers
(`resolution`, `checkout`, `audit`) validate inbound events against these schemas before touching
their `inbox` table. No runtime code lives here yet — schemas only, filled in alongside each
service's OpenAPI contract in Wave 4.
