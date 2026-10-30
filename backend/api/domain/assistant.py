# ruff: noqa: E501  (the catalogue is a table)

"""The in-app assistant's action catalogue and matcher (FS-045). Pure: no database.

Each action names the screen to open as a stable key the frontend maps to its own
route, and what a caller must hold to be shown it: any one of `requires`, each an
all-of set of `module.action` pairs (edge case 2). Holding it is for rendering only:
the screen's endpoints still enforce everything.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

Pair = tuple[str, str]

# every screen key the API may answer, so the generated doc lists them (edge case 7)
Screen = Literal[
    "leads.new", "leads.list", "leads.detail", "leads.duplicates", "leads.qr_codes",
    "customers.list", "customers.detail", "campaigns.list", "campaigns.new",
    "quotations.new", "quotations.list", "quotations.detail", "approvals.queue",
    "orders.new", "orders.list", "orders.detail", "dispatch.list",
    "payments.new", "payments.list", "complaints.new", "complaints.list", "complaints.detail",
    "tasks.new", "tasks.planner", "subsidy.applications", "subsidy.applications.new",
    "schemes.list", "rewards.list", "marketing.orders.new", "stock.list", "targets.list",
    "reports.list", "tracking.map", "messages.list", "partners.list", "users.list", "users.new",
    "products.list", "pricing.lists", "settings.holidays", "settings.company", "settings.lookups",
]


@dataclass(frozen=True)
class Action:
    key: str
    title: str
    hint: str
    screen: Screen
    requires: tuple[tuple[Pair, ...], ...]
    keywords: tuple[str, ...] = ()
    rank: int = 0                 # > 0: shown, in this order, when nothing is typed
    staff_only: bool = False
    module: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "module", self.requires[0][0][0])


def one(module: str, action: str) -> tuple[tuple[Pair, ...], ...]:
    return (((module, action),),)


CATALOGUE: tuple[Action, ...] = (
    Action("lead.create", "New lead", "Enter a farmer's enquiry", "leads.new", one("leads", "create"),
           ("add", "enquiry", "inquiry", "farmer", "create"), rank=1),
    Action("lead.list", "Leads", "Find and work your leads", "leads.list", one("leads", "view"),
           ("enquiries", "inquiries", "pipeline", "farmers"), rank=2),
    Action("lead.duplicates", "Duplicate leads", "Review pairs and merge", "leads.duplicates",
           one("leads", "edit"), ("merge", "duplicate", "same"), staff_only=True),
    Action("lead.qr", "QR codes", "Print a code that brings leads", "leads.qr_codes", one("leads", "create"),
           ("qr", "code", "banner", "leaflet", "print"), staff_only=True),
    Action("customer.list", "Customers", "A farmer's leads, quotations and orders in one place",
           "customers.list", one("leads", "view"), ("customer", "farmer", "history", "360")),
    Action("campaign.list", "Campaigns", "Marketing campaigns and what they brought", "campaigns.list",
           one("leads", "view"), ("campaign", "exhibition", "mela", "fair", "event"), staff_only=True),
    Action("campaign.create", "New campaign", "Record an exhibition, meeting or drive", "campaigns.new",
           one("campaigns", "create"), ("campaign", "exhibition", "mela", "add"), staff_only=True),
    Action("quotation.create", "New quotation", "Start from a qualified lead", "quotations.new",
           one("quotations", "create"), ("quote", "estimate", "price", "add"), rank=3),
    Action("quotation.list", "Quotations", "Sent, accepted and draft quotations", "quotations.list",
           one("quotations", "view"), ("quote", "quotes", "estimates")),
    Action("approvals", "Approvals", "Orders and discounts waiting for you", "approvals.queue",
           (((("sales_orders", "approve"),)), ((("quotations", "approve"),))),
           ("approve", "approval", "pending", "discount", "accounts", "queue"), rank=5, staff_only=True),
    Action("order.create", "New order", "From an accepted quotation, or direct", "orders.new",
           one("sales_orders", "create"), ("order", "sale", "book", "add"), rank=4),
    Action("order.list", "Orders", "Orders and their status", "orders.list", one("sales_orders", "view"),
           ("order", "orders", "sales")),
    Action("dispatch.record", "Record a dispatch", "Ship an approved order", "dispatch.list",
           one("dispatch", "create"), ("dispatch", "ship", "dc", "delivery", "challan"), staff_only=True),
    Action("payment.record", "Record a payment", "A receipt against orders", "payments.new",
           one("payments", "create"), ("payment", "receipt", "money", "collect", "cheque", "neft"), staff_only=True),
    Action("payment.list", "Payments", "Receipts and balances", "payments.list", one("payments", "view"),
           ("payment", "receipts", "balance", "outstanding", "ledger")),
    Action("complaint.create", "Raise a complaint", "Log a product or service problem", "complaints.new",
           one("complaints", "create"), ("complaint", "problem", "issue", "defect", "add")),
    Action("complaint.list", "Complaints", "Open and closed complaints", "complaints.list",
           one("complaints", "view"), ("complaint", "complaints", "issues", "sla")),
    Action("task.create", "New task", "A follow-up for you or your team", "tasks.new", one("tasks", "create"),
           ("task", "follow", "followup", "reminder", "todo", "add"), rank=6),
    Action("task.planner", "My day", "Today's tasks and visits", "tasks.planner", one("tasks", "view"),
           ("planner", "today", "tasks", "plan", "schedule")),
    Action("subsidy.list", "Subsidy applications", "Track an application stage by stage",
           "subsidy.applications", one("subsidy", "view"), ("subsidy", "ggrc", "application", "scheme")),
    Action("subsidy.create", "New subsidy application", "From a subsidised lead", "subsidy.applications.new",
           one("subsidy", "create"), ("subsidy", "ggrc", "application", "add")),
    Action("scheme.list", "Schemes", "Discounts and offers on orders", "schemes.list", one("schemes", "view"),
           ("scheme", "offer", "discount", "promotion")),
    Action("reward.list", "Rewards", "Points and redemptions", "rewards.list", one("rewards", "view"),
           ("reward", "points", "redeem", "gift")),
    Action("marketing.order", "Order marketing material", "Banners, caps, brochures", "marketing.orders.new",
           one("marketing_material", "create"), ("marketing", "material", "banner", "brochure", "kit")),
    Action("stock.list", "Stock", "What is in each warehouse", "stock.list", one("stock", "view"),
           ("stock", "inventory", "warehouse", "available")),
    Action("target.list", "Targets", "Targets and achievement", "targets.list", one("targets", "view"),
           ("target", "achievement", "goal")),
    Action("report.list", "Reports", "Conversion, sales, dealers, complaints, campaigns", "reports.list",
           one("reports", "view"), ("report", "reports", "excel", "analysis", "performance")),
    Action("tracking.team", "Team map", "Where your team is and their visits", "tracking.map",
           one("tracking", "view"), ("map", "location", "gps", "visit", "team"), staff_only=True),
    Action("chat.open", "Messages", "Chat with a colleague", "messages.list", one("chat", "view"),
           ("chat", "message", "talk"), staff_only=True),
    Action("partner.list", "Dealers", "Dealers and distributors", "partners.list", one("partners", "view"),
           ("dealer", "distributor", "partner", "channel")),
    Action("user.list", "Users", "Staff accounts and roles", "users.list", one("users", "view"),
           ("user", "staff", "employee", "account", "role"), staff_only=True),
    Action("user.create", "Add a user", "A staff account", "users.new", one("users", "create"),
           ("user", "staff", "employee", "add", "account"), staff_only=True),
    Action("product.list", "Products", "The product catalogue", "products.list", one("products", "view"),
           ("product", "item", "catalogue", "pipe", "dripline")),
    Action("pricing.list", "Price lists", "Prices by state and channel", "pricing.lists", one("pricing", "view"),
           ("price", "rate", "list", "pricing")),
    Action("masters.holidays", "Holidays", "Days complaint targets skip", "settings.holidays",
           one("masters", "edit"), ("holiday", "calendar", "leave"), staff_only=True),
    Action("masters.settings", "Settings", "Company settings", "settings.company", one("masters", "edit"),
           ("setting", "settings", "configure", "portal"), staff_only=True),
    Action("masters.lookups", "Lists and options", "Lead sources, crops, reasons", "settings.lookups",
           one("masters", "edit"), ("source", "crop", "reason", "lookup", "option"), staff_only=True),
)

_WORD = re.compile(r"[\w/]+", re.UNICODE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def has_control(text: str) -> bool:
    return bool(_CONTROL.search(text))


def words(text: str) -> list[str]:
    return [unicodedata.normalize("NFC", w).lower() for w in _WORD.findall(text)]


def held_by(a: Action, held: set[Pair]) -> bool:
    return any(all(p in held for p in alt) for alt in a.requires)


def _score(a: Action, query: list[str]) -> int:
    """Every query word must start a word of the title or keywords; a title hit
    counts double. 0 means no match."""
    title, keys = words(a.title), [w for k in a.keywords for w in words(k)]
    total = 0
    for q in query:
        if any(w.startswith(q) for w in title):
            total += 2
        elif any(w.startswith(q) for w in keys):
            total += 1
        else:
            return 0
    return total


def allowed(held: set[Pair], *, staff: bool) -> list[Action]:
    return [a for a in CATALOGUE if held_by(a, held) and (staff or not a.staff_only)]


def match(q: str | None, held: set[Pair], *, limit: int = 8, staff: bool = True) -> list[Action]:
    """The actions the caller holds that match `q`, best first; with no words, the
    starter set in `rank` order (hand-picked, edge case 6)."""
    mine = allowed(held, staff=staff)
    query = words(q or "")
    if not query:
        return sorted((a for a in mine if a.rank), key=lambda a: a.rank)[:limit]
    scored = [(s, i, a) for i, a in enumerate(mine) if (s := _score(a, query))]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [a for _, _, a in scored[:limit]]


# ── what the text looks like, for the record search ──────────────────────────

_DOC = re.compile(r"^\s*(pol|qt|so|cmp|comp|poly)\s*[/ ]?", re.IGNORECASE)


def mobile_digits(q: str) -> str | None:
    """Digits to look for in a mobile: 4 or more, with +91, 91 or 0 in front taken
    off (edge case 8). None when q is not a number."""
    if re.search(r"[^\d\s+()-]", q):
        return None
    d = re.sub(r"\D", "", q)
    if len(d) > 10 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    return d if len(d) >= 4 else None


def looks_like_document(q: str) -> bool:
    return bool(_DOC.match(q)) and "/" in q


def serial(q: str) -> str | None:
    """3 to 6 digits alone: a document's serial, padded as numbers are (edge case 10)."""
    s = q.strip()
    return s.zfill(5) if s.isdigit() and 3 <= len(s) <= 6 else None


def name_text(q: str) -> str | None:
    """Text for a name search: at least 3 characters that are not digits or
    punctuation. Vowel signs count, so a Gujarati or Hindi name qualifies (edge case 12)."""
    s = " ".join(q.split())
    letters = [c for c in s if not c.isdigit() and unicodedata.category(c)[0] not in ("P", "Z", "S")]
    return s if len(letters) >= 3 else None
