"""Scheduled jobs.

Populated as features land. FS-001 contributes the retention purge for `session`
and `login_attempt` (EC-15): both hold IP addresses against named identifiers,
which is personal data under DPDP, and every other table here already has a
retention answer.
"""

from __future__ import annotations

from arq import cron

from worker.jobs.outbox import outbox_drain, purge_expired_sessions

CRON_JOBS: list = [
    # Every ten seconds. An OTP that arrives a minute after it was asked for is a
    # support call, and the query is a partial-index lookup that finds nothing
    # almost every time it runs.
    cron(outbox_drain, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
    # Nightly, off-peak. Deleting personal data is not urgent; doing it at all is.
    cron(purge_expired_sessions, hour=3, minute=17),
]
