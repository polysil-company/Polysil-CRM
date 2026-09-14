# Polysil CRM

Monorepo for the Polysil Irrigation Systems CRM: backend API, and the web and
mobile clients.

| Directory | What |
|---|---|
| `backend/` | FastAPI + PostgreSQL API, background worker, migrations, tests |
| `frontend/` | web and mobile clients (coming) |

The backend is the API the clients build against. Its contract is generated into
`backend/docs/api/`, one file per module. To run the backend, see
[`backend/README.md`](backend/README.md).
