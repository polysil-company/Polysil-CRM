"""Put failed quotation and order PDFs back in the render queue.

    python scripts/requeue_pdfs.py

A render that fails five times stays `failed` (FS-005, FS-012). Before R2 existed on
staging every render failed that way (ISS-094), so once storage works those
documents need one more go. This resets them to `pending` with a fresh attempt
count; the worker renders them on its next pass.

It sends nothing by itself. A quotation's share link goes out after its render
only while `WHATSAPP_TEMPLATE_QUOTATION_SHARE` is set, and an order's messages
went out at approval, not at render.

Run it only once storage works on the box (the API reports `storage_available` on
`GET /complaints/stats`): otherwise each render fails five times again. The tools
container cannot check that itself, because compose gives it no R2 settings, and
it needs none to reset rows.

Runs as the table owner (the tools container's connection), like
`sync_message_templates.py`. Cancelled orders are left alone: their PDF is
withdrawn on cancel.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# run as `python scripts/...`: the repository root is not on the path otherwise
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from api.db.session import async_session_factory  # noqa: E402


async def requeue() -> int:
    async with async_session_factory() as session, session.begin():
        quotations = (await session.execute(text(
            "UPDATE quotation SET pdf_state = 'pending', pdf_attempts = 0, pdf_error = NULL, "
            "pdf_next_attempt_at = now(), pdf_lease_until = NULL, pdf_lease_token = NULL "
            "WHERE pdf_state = 'failed' RETURNING id"))).all()
        orders = (await session.execute(text(
            "UPDATE sales_order SET pdf_state = 'pending', pdf_attempts = 0, pdf_error = NULL, "
            "pdf_next_attempt_at = now(), pdf_lease = NULL, pdf_lease_until = NULL "
            "WHERE pdf_state = 'failed' AND status <> 'cancelled' RETURNING id"))).all()
    print(f"requeue-pdfs: {len(quotations)} quotation(s) and {len(orders)} order(s) "
          "back in the queue")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(requeue()))
