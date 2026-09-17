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

## whatsapp_smoke.py: one real send, by hand

```
python scripts/livetest/whatsapp_smoke.py --to 91XXXXXXXXXX --template auth.otp
python scripts/livetest/whatsapp_smoke.py --to 91XXXXXXXXXX --template lead_ack
```

The only place this project sends a real WhatsApp message outside a deployment (FS-007 rule 19). It needs `WHATSAPP_PROVIDER=11za` and `WHATSAPP_AUTH_TOKEN`, refuses to run without a number, and prints sanitised fields only: the token and every value sent are replaced by `***`. Its purpose is the first contact with the client's account: the executed responses fill the spec's recognised error shapes (W6), settle the copy-code button (W8), the message id (W9) and the template listing's fields (W10), and size `whatsapp_send_timeout`. Record them in FS-007 section 9, sanitised.

The three drivers above read the sign-in code out of the outbox. That still works on a local box with the mock provider: the outbox keeps the payload there (rule 12's stated exception). Against a real provider the code is on the phone, not in the table.
