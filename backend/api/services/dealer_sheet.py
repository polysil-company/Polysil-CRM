# ruff: noqa: E501  (template values inline)

"""The partner data sheet as a PDF (FS-071): the client's "Dealer Data Sheet",
filled from an application or blank.

Rendered when asked, in the API, not stored (spec section 5, plan review R-5):
- the data is read first and the render runs in a thread;
- at most two render at once in a process, a third answers 503 `busy`, because
  WeasyPrint's layout holds the GIL and each render keeps the request's pooled
  connection open (edge E-10);
- autoescape is on and nothing is marked safe; the renderer fetches no URL but the
  bundled logo (E-12);
- the bank account is masked to its last 4 for everyone (GAP-518).
"""

from __future__ import annotations

import asyncio
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from api.config import get_settings
from api.errors import ServiceUnavailableError
from api.pdf import env as _env
from api.pdf import logo as _logo
from api.pdf import logo_only_fetcher, render_pdf, render_slot, renderer_available


def _money(v: Any) -> str:
    """12,34,567.89, as the quotation prints it."""
    try:
        d = Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return str(v)
    whole, frac = f"{abs(d):.2f}".split(".")
    if len(whole) > 3:
        head, groups = whole[:-3], [whole[-3:]]
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        groups.insert(0, head)
        whole = ",".join(groups)
    return ("-" if d < 0 else "") + whole + "." + frac


def masked(account: str | None) -> str | None:
    if not account:
        return account
    return "x" * max(len(account) - 4, 0) + account[-4:]


_FIRM = {"proprietorship": "Proprietary", "partnership": "Partnership", "llp": "LLP", "company": "Company"}
_SCOPE = {"supply": "Supply", "installation": "Installation", "both": "Supply and installation"}


def context(app: dict[str, Any] | None, *, partner_type: str) -> dict[str, Any]:
    """The template's values. `app` None is the blank sheet."""
    if app is None:
        return {"blank_capital": 3, "blank_manpower": 4, "blank_installations": 4, "working_capital": [],
                "manpower": [], "previous_installations": [], "unit": "sq. m / sq. ft",
                "deposit_text": "________________", "role_word": partner_type.upper()}
    s = dict(app)
    deposit = s.get("deposit") or {}
    status = deposit.get("status")
    s["deposit_kind"] = status
    if status == "paid":
        s["deposit_text"] = _money(deposit.get("paid_amount"))
        s["deposit_note"] = f"Paid on {deposit.get('paid_on')}" + (
            f", reference {deposit.get('reference')}" if deposit.get("reference") else "") + "."
    elif status == "waived":
        s["deposit_text"] = _money(deposit.get("amount_set"))
    elif status == "pending":
        # the blank to fill in by hand, never "has been paid" for money not received (F-6)
        s["deposit_text"] = "________________"
        s["deposit_note"] = f"Rs. {_money(deposit.get('amount_due'))} is due and not yet recorded as paid."
    s["bank_account_no"] = masked(s.get("bank_account_no"))
    s["firm_type"] = _FIRM.get(s.get("firm_type") or "", s.get("firm_type"))
    s["unit"] = "sq. m" if s.get("area_unit") == "sq_m" else "sq. ft"
    s["role_word"] = (s.get("partner_type") or partner_type).upper()
    s["working_capital"] = s.get("working_capital") or []
    s["manpower"] = s.get("manpower") or []
    s["previous_installations"] = [{**r, "scope": _SCOPE.get(str(r.get("scope")), r.get("scope"))}
                                   for r in s.get("previous_installations") or []]
    s["blank_capital"] = 0 if s["working_capital"] else 1
    s["blank_manpower"] = 0 if s["manpower"] else 1
    s["blank_installations"] = 0 if s["previous_installations"] else 1
    for k in ("other_sources_lakhs", "working_capital_total_lakhs"):
        if s.get(k) is not None:
            s[k] = _money(s[k])
    if s.get("mobile"):
        m = str(s["mobile"])
        s["mobile"] = "+91 " + m[-10:] if len(m) >= 10 else m
    return s


def html(app: dict[str, Any] | None, *, partner_type: str) -> str:
    word = partner_type.upper()
    return _env.get_template("dealer_sheet.html").render(
        s=context(app, partner_type=partner_type), logo=_logo(),
        heading=f"{word} DATA SHEET", title=f"{word.capitalize()} data sheet")


def filename(label: str) -> str:
    """ASCII, so any firm name makes a valid header (E-11)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-.") or "sheet"
    return f"Data-Sheet-{safe[:60]}"


async def render(app: dict[str, Any] | None, *, partner_type: str) -> tuple[bytes, str]:
    """(body, content type). `pdf_renderer = "html"` answers the HTML, for a box
    without the renderer's libraries, as the quotation does."""
    page = html(app, partner_type=partner_type)
    if get_settings().pdf_renderer == "html":
        return page.encode("utf-8"), "text/html; charset=utf-8"
    if renderer_available():
        raise ServiceUnavailableError("PDFs cannot be made right now.", code="pdf_unavailable")
    with render_slot():
        return await asyncio.to_thread(render_pdf, page, logo_only_fetcher()), "application/pdf"


_blank: dict[str, tuple[bytes, str]] = {}


async def blank(partner_type: str) -> tuple[bytes, str]:
    """The blank sheet, rendered once per type in a process."""
    if partner_type not in _blank:
        _blank[partner_type] = await render(None, partner_type=partner_type)
    return _blank[partner_type]
