"""Scheduled jobs.

Populated as features land. FS-001 contributes the retention purge for `session`
and `login_attempt` (EC-15): both hold IP addresses against named identifiers,
which is personal data under DPDP, and every other table here already has a
retention answer.
"""

from __future__ import annotations

from arq import cron

from worker.jobs.outbox import outbox_drain, purge_expired_sessions
from worker.jobs.quotations import quotation_expire, quotation_render_due

CRON_JOBS: list = [
    # Every ten seconds. An OTP that arrives a minute after it was asked for is a
    # support call, and the query is a partial-index lookup that finds nothing
    # almost every time it runs.
    cron(outbox_drain, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
    # Nightly, off-peak. Deleting personal data is not urgent; doing it at all is.
    cron(purge_expired_sessions, hour=3, minute=17),
    # FS-005: a sent quotation's PDF, within seconds of the send. One lease per
    # document; the claim finds nothing almost every time it runs.
    cron(quotation_render_due, second={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
         run_at_startup=True),
    # 00:05 IST is 18:35 UTC. arq computes the next run from the process clock, so
    # worker/main.py asserts TZ is UTC (plan review R-18); the date itself is
    # passed in as today_ist(), never read from current_date.
    cron(quotation_expire, hour=18, minute=35),
]
