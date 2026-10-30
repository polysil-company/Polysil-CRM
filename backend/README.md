# Polysil CRM — backend

CRM, dealer portal and field-sales backend for Polysil Irrigation Systems: a
micro-irrigation manufacturer selling across several Indian states, mostly through
government subsidy schemes.

FastAPI, PostgreSQL and row-level security. Authorization is enforced twice, in the
service layer and in the database, from one declaration per module.

## Running it

```bash
cp infra/.env.example infra/.env      # fill in DB creds, JWT_SECRET
docker compose --profile tunnel up -d # or --profile local for a throwaway Postgres
python scripts/dev.py check           # stack up + reference-SQL checks
pytest -q                             # the full suite
```

Everything reaches the database at `127.0.0.1:6432` through PgBouncer in transaction
mode. A direct connection is not supported: the `SET LOCAL` claim propagation that
authorization depends on only behaves correctly through the pooler.

## Layout

| Path | What |
|---|---|
| `api/` | app factory, routers, services, schemas, domain logic, migrations |
| `api/domain/` | pure business logic, no database (kept fast and unit-testable) |
| `api/db/migrations/` | Alembic migrations, including the RLS policies |
| `worker/` | background jobs (the outbox drain) |
| `tests/` | unit, service, API and RLS tests; Postgres is never mocked |
| `scripts/` | dev stack, migrations, doc and graph generators |
| `docs/api/` | the API contract, generated from the live schema |
| `infra/` | docker-compose and the env template |

## The API contract

`docs/api/` is generated from the running application, one file per module. It is
what a client builds against. Regenerate it after any endpoint change:

```bash
python scripts/generate_api_docs.py
```

## Conventions

- Money is `Decimal` / `numeric(14,2)`, never a float.
- Every mutation takes an `Idempotency-Key`.
- Every state change writes an `activity_event` in the same transaction.
- Outbound messages go to the outbox, never sent inside a request.
- Services never commit; the request dependency owns the transaction boundary.
- Migrations are hand-reviewed: autogenerate does not emit policies or triggers.
