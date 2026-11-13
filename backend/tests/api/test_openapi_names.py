"""Two schema classes with one name make OpenAPI qualify both as
`api__schemas__<module>__<Name>`. That renames the other module's shape in the
generated docs and in any client generated from the schema (ADR-028), so it is a
breaking change made by accident. FS-009 did it once with PageMeta and TerritoryRef.

The names below were qualified before this guard (ISS-106). Renaming them is itself
a breaking change, so they stay until both tracks agree; nothing may join them."""

from __future__ import annotations

from api.main import app

KNOWN = {
    "api__schemas__auth__Envelope_list_Assignee____1",
    "api__schemas__auth__Envelope_list_Assignee____2",
    "api__schemas__auth__PartnerRef", "api__schemas__complaints__Assignee",
    "api__schemas__complaints__LinesReplace", "api__schemas__leads__Assignee",
    "api__schemas__leads__PartnerRef", "api__schemas__messages__MarkRead",
    "api__schemas__messages__ResourceRef", "api__schemas__notifications__MarkRead",
    "api__schemas__notifications__ResourceRef", "api__schemas__quotations__LinesReplace",
    "api__schemas__users__PartnerRef",
}


def test_no_new_component_schema_name_is_module_qualified() -> None:
    names = app.openapi()["components"]["schemas"]
    qualified = {n for n in names if n.startswith("api__schemas__")}
    assert qualified <= KNOWN, sorted(qualified - KNOWN)
