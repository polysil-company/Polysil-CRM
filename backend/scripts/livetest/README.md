# Live test drivers

End-to-end checks over real HTTP against a running API and the seeded demo
users. Not pytest: these print a PASS/FAIL report and leave their leads in the
database so you can look at them.

```bash
python scripts/seed_demo.py                                   # demo users, roles, hierarchy
python -m uvicorn api.main:app --host 127.0.0.1 --port 8100   # port 8000 may be taken
python scripts/livetest/auth_and_create.py                    # auth flows, create, read, RLS scoping
python scripts/livetest/lifecycle.py                          # transition, reopen, notes, timeline
python scripts/livetest/assign_edit_duplicates_admin.py       # assign, PATCH, delete, duplicates, merge, admin
```

The dealer signs in by OTP; the drivers read the code from `notification_outbox`
the way a real client would receive it. They read database credentials from
`infra/.env`.

## What the drivers leave behind

Leads, notes, duplicate links and events stay in the database on purpose: they are
the data to look at afterwards. The admin driver also adds one lost reason
(`live_reason_<hex>`) and switches it off; nothing removes lookup items (ADR-033),
so every run adds one. The suite tolerates them: it checks the seeded codes rather
than counting rows, and picks an active reason when it needs one.
