# Polysil CRM

Monorepo for the Polysil Irrigation Systems CRM: the backend API, and the web and
mobile clients.

| Directory | What |
|---|---|
| `backend/` | FastAPI + PostgreSQL API, background worker, migrations, tests |
| `Frontend/` | Next.js web client |

The backend is the API the clients build against. Its contract is generated into
[`backend/docs/api/`](backend/docs/api/), one file per module, and the notes that
contract cannot carry are in [`backend/docs/handover/`](backend/docs/handover/).
To run the backend, see [`backend/README.md`](backend/README.md).

## Branches

| Branch | Role |
|---|---|
| `main` | production |
| `staging` | release candidate: user and load testing happens here |
| `integration` | everything merged, checks green |
| feature branches, e.g. `backend-foundation`, `frontend-foundation` | work in progress |

Code is promoted one step at a time and never committed to `integration`,
`staging` or `main` directly:

```
feature branch ─▶ integration ─▶ staging ─▶ main
                  checks pass    reviewed   tested
```

Each arrow is a pull request, and each has its own bar. Into `integration`, the
automated checks. Into `staging`, a review. Into `main`, user and load testing on
what `staging` is running.

## Checks and automation

Pull requests into `integration`, `staging` and `main` run automated checks,
commits that reach those branches are checked again, and a nightly run watches
`integration`. [docs/CI-CD.md](docs/CI-CD.md) explains what runs and when, and the
team rules our GitHub plan cannot enforce.
