# Polysil CRM

Monorepo for the Polysil Irrigation Systems CRM.

## Branches

| Branch | Role |
|---|---|
| `main` | production |
| `integration` | staging |
| feature branches (e.g. `backend-foundation`) | work in progress |

Application code is promoted through `integration` and then into `main`. It is not
committed to `main` directly. See the `backend-foundation` branch for the current
backend (FastAPI + PostgreSQL API, worker, migrations, tests).
