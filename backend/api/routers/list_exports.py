"""FS-081: an export beside every list that lacked one.

Each export is registered from its list route, not written out by hand: it takes the
list route's own `dependencies` (so its gate is the list's, plan review EC-3), the
list's own filters (`filters_of`), and calls the list handler as the caller (so its
rows, scope and blank cells are the list's, rules 1 and 5). It is placed straight
after the list route, before any `/{id}` route that would otherwise match
`/export` first (EC-7).

Imported by `api/main.py` before the routers are included.
"""

# No `from __future__ import annotations`: export_list's annotations must resolve when
# it is defined, because they name the per-route filters dependency, a local.

import inspect
from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from fastapi.routing import APIRoute

from api.deps import CallerDep, Claims, DbSession
from api.routers import (
    campaigns,
    customers,
    dealer_applications,
    holidays,
    masters,
    payments,
    pricing,
    products,
    ratings,
    rewards,
    schemes,
    seller_gstins,
    stock,
    subsidy_schemes,
    warranty,
)
from api.routers.exporting import EXPORT_RESPONSE, ExportFormat, export, filters_of
from api.schemas.auth import ErrorResponse
from api.services import exports

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not signed in."},
    403: {"model": ErrorResponse, "description": "Refused exactly as the list is refused."},
    **EXPORT_RESPONSE,
}

Stem = str | Callable[[dict[str, Any]], str]

# every list route given an export here, with its columns: the column-path test reads
# each route's item model from this
REGISTERED: list[tuple[APIRoute, Sequence[exports.Column]]] = []


def add_export(router: APIRouter, list_path: str, *, stem: Stem, title: str,
               columns: Sequence[exports.Column], what: str, once: bool = False) -> None:
    """Register `GET <list_path>/export` on `router`, right after the list route.

    `list_path` is relative to the router's prefix ("" for the router's root list).
    `once` drains the list in one call (page-number lists, offset cursors and
    unpaged lists); otherwise the cursor is followed.
    """
    full = router.prefix + list_path
    route = next(r for r in router.routes
                 if isinstance(r, APIRoute) and r.path == full and "GET" in r.methods)
    endpoint = route.endpoint
    filters_dep = filters_of(endpoint)
    # the route's own gates; add_api_route adds the router's again by itself
    own = [d for d in route.dependencies if d not in router.dependencies]
    # handlers name their unused claims dependency `_` or `_claims` (plan review S-4)
    params = inspect.signature(endpoint, eval_str=True).parameters
    unused = [n for n in params if n.startswith("_")]
    # they get claims, so they must be claims: a `_: CallerDep` would get the wrong
    # type and no test would notice (code review F-4)
    wrong = [n for n in unused if params[n].annotation != Claims]
    if wrong:
        raise TypeError(f"{endpoint.__name__}: {wrong} are not Claims; pass them by name")

    async def export_list(db: DbSession, caller: CallerDep, claims: Claims,
                          filters: Annotated[dict[str, Any], Depends(filters_dep)],
                          fmt: ExportFormat = "xlsx") -> Response:
        name = stem(filters) if callable(stem) else stem
        # `_` and `claims` reach handlers that take an unused claims dependency
        # (plan review S-4); export() passes only the names the handler accepts
        return await export(endpoint, stem=name, title=title, columns=columns,
                            user_id=caller.user_id, filters=filters, fmt=fmt, once=once,
                            db=db, caller=caller, claims=claims, **dict.fromkeys(unused, claims))

    export_list.__name__ = f"export_{endpoint.__name__}"
    router.add_api_route(
        list_path + "/export", export_list, methods=["GET"], response_class=Response,
        responses=_ERRORS, dependencies=own, name=export_list.__name__,
        summary=f"Export {what}",
        description=(
            f"Download {what} as Excel (`format=xlsx`, the default) or CSV, with the same "
            "filters as the list. The file holds exactly the rows the list would show for "
            "these filters, across every page, and nothing outside your scope; a value the "
            "list hides from you is a blank cell. Refused exactly where the list is refused. "
            "More than 5,000 rows is `422 export_too_large`: narrow the filters. Call it "
            "with `fetch` and the bearer token, then save the blob."))
    added = router.routes.pop()
    router.routes.insert(router.routes.index(route) + 1, added)
    REGISTERED.append((route, columns))


def _price_list_stem(filters: dict[str, Any]) -> str:
    # two lists' files must not share a name (EC-8)
    return f"price-list-items-{str(filters.get('list_id', ''))[:8]}"


add_export(products.router, "", stem="products", title="Products", columns=exports.PRODUCTS,
           what="the product catalogue", once=True)
add_export(products.tax_rates, "", stem="tax-rates", title="Tax rates", columns=exports.TAX_RATES,
           what="the GST rates by HSN", once=True)
add_export(pricing.price_lists, "", stem="price-lists", title="Price lists",
           columns=exports.PRICE_LISTS, what="the price lists", once=True)
add_export(pricing.price_lists, "/{list_id}/items", stem=_price_list_stem, title="Price list items",
           columns=exports.PRICE_LIST_ITEMS, what="one price list's rates", once=True)
add_export(customers.router, "", stem="customers", title="Customers", columns=exports.CUSTOMERS,
           what="the customers")
add_export(stock.router, "", stem="stock", title="Stock", columns=exports.STOCK,
           what="stock balances", once=True)
add_export(stock.router, "/movements", stem="stock-movements", title="Stock movements",
           columns=exports.STOCK_MOVEMENTS, what="stock movements")
add_export(stock.warehouses, "", stem="warehouses", title="Warehouses", columns=exports.WAREHOUSES,
           what="the warehouses", once=True)
add_export(payments.router, "", stem="payments", title="Payments", columns=exports.PAYMENTS,
           what="the payments")
add_export(warranty.terms, "", stem="warranty-terms", title="Warranty terms",
           columns=exports.WARRANTY_TERMS, what="the warranty terms", once=True)
add_export(masters.org_units, "", stem="offices", title="Offices", columns=exports.ORG_UNITS,
           what="the offices")
add_export(masters.territories, "", stem="territories", title="Territories",
           columns=exports.TERRITORIES, what="the territories")
add_export(dealer_applications.router, "", stem="dealer-applications", title="Dealer applications",
           columns=exports.DEALER_APPLICATIONS, what="the dealer applications", once=True)
add_export(campaigns.router, "", stem="campaigns", title="Campaigns", columns=exports.CAMPAIGNS,
           what="the campaigns", once=True)
add_export(schemes.router, "", stem="schemes", title="Schemes", columns=exports.SCHEMES,
           what="the dealer schemes")
add_export(schemes.entitlements, "", stem="scheme-entitlements", title="Scheme entitlements",
           columns=exports.SCHEME_ENTITLEMENTS, what="the scheme entitlements")
add_export(rewards.router, "/ledger", stem="reward-points", title="Reward points",
           columns=exports.REWARD_LEDGER, what="the reward points ledger")
add_export(rewards.router, "/gift-redemptions", stem="gift-redemptions", title="Gift redemptions",
           columns=exports.GIFT_REDEMPTIONS, what="the gift redemptions")
add_export(rewards.rules, "", stem="reward-rules", title="Reward rules",
           columns=exports.REWARD_RULES, what="the reward rules", once=True)
add_export(rewards.gifts, "", stem="gifts", title="Gifts", columns=exports.GIFTS,
           what="the gift catalogue", once=True)
add_export(subsidy_schemes.router, "", stem="subsidy-schemes", title="Subsidy schemes",
           columns=exports.SUBSIDY_SCHEMES, what="the subsidy schemes", once=True)
add_export(holidays.router, "", stem="holidays", title="Holidays", columns=exports.HOLIDAYS,
           what="the holidays", once=True)
add_export(seller_gstins.router, "", stem="seller-gstins", title="Seller GSTINs",
           columns=exports.SELLER_GSTINS, what="the company's GSTINs", once=True)
add_export(ratings.router, "", stem="ratings", title="Ratings", columns=exports.RATINGS,
           what="the ratings")
