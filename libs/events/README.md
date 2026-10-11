# libs/events

Shared outbox/inbox event-envelope code (no business logic): the `Event` wrapper shape, the
`SELECT ... FOR UPDATE SKIP LOCKED` outbox-scan helper, and the `INSERT ... ON CONFLICT DO NOTHING`
inbox-dedupe helper described in `architecture/data-architecture.md` §7. Event *schemas* (the
contracts) live in `contracts/events/schemas/`, not here — this package only reads/writes against
those schemas. No code here yet; added alongside the first service (mandate or checkout) that
needs the outbox relay in Wave 5.
