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
backend (FastAPI + PostgreSQL API, worker, migrations, tests), and the
`frontend-foundation` branch for the current frontend (Next.js, in `Frontend/`).

## Checks and automation

Pull requests into `integration` and `main` run automated checks, commits that reach
those branches are checked again, and a nightly run watches `integration`.
[docs/CI-CD.md](docs/CI-CD.md) explains what runs and when, and the team rules our
GitHub plan can't enforce.
