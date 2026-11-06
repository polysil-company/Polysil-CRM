"""What an email says (FS-078 section 5): built at send from what the resolver
returns. Titles, times and links only, never a notice's body (EC-7). The morning
summary carries two counts and a link, never task titles.

Links come from the record's type and uuid through the same table the bell uses
(the frontend's `resourceHref`); anything else opens the CRM (EC-22).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from jinja2 import Environment

IST = ZoneInfo("Asia/Kolkata")
LISTED = 20
FOOTER = "Turn these emails off in your profile."

# the frontend's resource-href.ts; a partner user has one portal page
STAFF_ROUTES: dict[str, str] = {
    "lead": "/leads/{id}",
    "quotation": "/quotations/{id}",
    "sales_order": "/sales-orders/{id}",
    "complaint": "/complaints/{id}",
    "subsidy_application": "/subsidy/{id}",
}
STAFF_HOME = "/dashboard"
PARTNER_HOME = "/portal"
PLANNER = "/my-tasks"

_env = Environment(autoescape=True, trim_blocks=True, lstrip_blocks=True)

_NOTICES_HTML = _env.from_string("""<!doctype html>
<html><body style="font-family: Arial, sans-serif; color: #1f2933;">
<p>Hello {{ name }},</p>
<p>{{ lead }}</p>
<ul>
{% for n in notices %}
<li><a href="{{ n.link }}">{{ n.title }}</a><br><small>{{ n.when }}</small></li>
{% endfor %}
</ul>
{% if more %}<p><a href="{{ home }}">And {{ more }} more in Polysil CRM.</a></p>{% endif %}
<p><small>{{ footer }}</small></p>
</body></html>""")

_MORNING_HTML = _env.from_string("""<!doctype html>
<html><body style="font-family: Arial, sans-serif; color: #1f2933;">
<p>Good morning {{ name }},</p>
<ul>
<li>Tasks due today: {{ due_today }}</li>
<li>Tasks overdue: {{ overdue }}</li>
</ul>
<p><a href="{{ link }}">Open your tasks</a></p>
<p><small>{{ footer }}</small></p>
</body></html>""")


@dataclass(frozen=True)
class Notice:
    title: str
    created_at: dt.datetime
    resource_type: str | None
    resource_id: str | None


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


def link(base: str, user_type: str, resource_type: str | None, resource_id: str | None) -> str:
    base = base.rstrip("/")
    if user_type == "partner_user":
        return base + PARTNER_HOME
    route = STAFF_ROUTES.get(resource_type or "")
    if route is None or not resource_id:
        return base + STAFF_HOME
    return base + route.format(id=resource_id)


def when(at: dt.datetime) -> str:
    return at.astimezone(IST).strftime("%d %b %Y, %H:%M IST")


def notices(base: str, name: str, user_type: str, items: list[Notice], total: int) -> Rendered:
    """`total` is how many were queued with this email; the rest go to the bell (EC-9)."""
    shown = items[:LISTED]
    total = max(total, len(items))
    rows = [{"title": " ".join(n.title.split()), "when": when(n.created_at),
             "link": link(base, user_type, n.resource_type, n.resource_id)} for n in shown]
    subject = (rows[0]["title"] if total == 1 else f"{total} updates in Polysil CRM")
    lead = ("You have an update you have not seen." if total == 1
            else f"You have {total} updates you have not seen.")
    more = total - len(shown)
    home = base.rstrip("/") + (PARTNER_HOME if user_type == "partner_user" else STAFF_HOME)
    text_lines = [f"Hello {name},", "", lead, ""]
    for r in rows:
        text_lines += [r["title"], f"  {r['when']}", f"  {r['link']}", ""]
    if more:
        text_lines += [f"And {more} more in Polysil CRM: {home}", ""]
    text_lines.append(FOOTER)
    html = _NOTICES_HTML.render(name=name, lead=lead, notices=rows, more=more, home=home,
                                footer=FOOTER)
    return Rendered(subject, "\n".join(text_lines), html)


def morning(base: str, name: str, user_type: str, due_today: int, overdue: int) -> Rendered:
    target = base.rstrip("/") + (PARTNER_HOME if user_type == "partner_user" else PLANNER)
    parts = []
    if due_today:
        parts.append(f"{due_today} due today")
    if overdue:
        parts.append(f"{overdue} overdue")
    subject = "Your tasks: " + ", ".join(parts or ["nothing due"])
    text = "\n".join([f"Good morning {name},", "", f"Tasks due today: {due_today}",
                      f"Tasks overdue: {overdue}", "", f"Open your tasks: {target}", "", FOOTER])
    html = _MORNING_HTML.render(name=name, due_today=due_today, overdue=overdue, link=target,
                                footer=FOOTER)
    return Rendered(subject, text, html)
