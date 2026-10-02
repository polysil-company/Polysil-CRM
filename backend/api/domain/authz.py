"""Authorization, the pure half.

FS-002 section 5.3: one declaration per module, from which three things are
generated. This module holds the declaration (`ScopeSpec`), the matrix parser
that turns `RBAC.md` section 6 into permission rows, and nothing that touches a
database. Rule 1: no SQLAlchemy here. The SQL emitter and the predicate builder
live in `api/authz/`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

SCOPES: tuple[str, ...] = ("own", "org_subtree", "territory", "partner_subtree", "global")
ACTIONS: tuple[str, ...] = ("view", "create", "edit", "approve", "delete")

_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")


class DeclarationError(ValueError):
    """A ScopeSpec that cannot be built. Raised at import, never at query time."""


@dataclass(frozen=True)
class ScopeSpec:
    """Which columns on one table carry which scope.

    A scope with no column emits no branch, in the policy and in the predicate
    alike. That is a declaration, not a silent miss: a role whose seeded scope for
    this module has no branch here is caught by the parity suite.

    `org_subtree_via` is the partners case (GAP-036): the table has no org-unit
    column, so a manager's org reach is resolved through the territories their org
    units cover. A read reaches the rows at, under or above those territories: the
    dealers that serve the caller's area, a district dealer for a taluka office and
    a state distributor for everyone in the state. A write reaches only at or under
    them, so a district office cannot edit a state distributor (FS-020).
    `parent_fallback` maps a parent column to a boolean function that admits a
    parent the caller cannot read directly: a dealer on a lead or quotation the
    caller can see (FS-020 rule 1). The INSERT check and the parent guard both use
    it. `parents` are the foreign keys a row attaches to; each gets a
    `WITH CHECK (EXISTS ...)` in the policy and a stage-4 lookup in the service
    (FS-002 5.2 fact 5, both halves). `self_column` with `self_ref` exempts the
    caller's own row from the view-permission gate: `app_user.id` against the
    caller's user id, so /auth/me works without `users.view`; `channel_partner.id`
    against the caller's partner, so a dealer can read their own partner row
    without `partners.view`.
    """

    module: str
    table: str
    own: str | None = None
    org_subtree: str | None = None
    org_subtree_via: str | None = None
    territory: str | None = None
    partner_subtree: str | None = None
    soft_delete: str | None = "deleted_at"
    parents: Mapping[str, str] = field(default_factory=dict)
    self_column: str | None = None
    self_ref: str | None = None  # "user" or "partner"; required with self_column
    parent_fallback: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        names = [self.module, self.table, *self.parents.values()]
        columns = [c for c in (self.own, self.org_subtree, self.org_subtree_via,
                               self.territory, self.partner_subtree, self.soft_delete,
                               self.self_column, *self.parents) if c is not None]
        for n in names + columns + list(self.parent_fallback.values()):
            if not _IDENT.match(n):
                raise DeclarationError(f"{self.module}: {n!r} is not a safe identifier")
        if self.org_subtree and self.org_subtree_via:
            raise DeclarationError(
                f"{self.module}: org_subtree and org_subtree_via are alternatives, not both")
        if not self.declared_scopes():
            raise DeclarationError(f"{self.module}: no scope branch declared")
        if (self.self_column is None) != (self.self_ref is None):
            raise DeclarationError(f"{self.module}: self_column and self_ref go together")
        if self.self_ref not in (None, "user", "partner"):
            raise DeclarationError(f"{self.module}: self_ref must be 'user' or 'partner'")
        stray = [c for c in self.parent_fallback if c not in self.parents
                 or self.parents[c] == self.table]
        if stray:
            raise DeclarationError(
                f"{self.module}: parent_fallback needs a cross-table parent: {stray}")

    def branch_column(self, scope: str) -> str | None:
        """The column a scope reads, or None when the scope has no branch here.
        `global` needs no column and returns None; use `has_branch` for it."""
        return {
            "own": self.own,
            "org_subtree": self.org_subtree or self.org_subtree_via,
            "territory": self.territory,
            "partner_subtree": self.partner_subtree,
            "global": None,
        }[scope]

    def has_branch(self, scope: str) -> bool:
        return scope == "global" or self.branch_column(scope) is not None

    def declared_scopes(self) -> tuple[str, ...]:
        return tuple(s for s in SCOPES if s != "global" and self.branch_column(s) is not None)

    def self_parent(self) -> str | None:
        """The column, if any, that points at another row of this same table."""
        for col, parent in self.parents.items():
            if parent == self.table:
                return col
        return None

    def indexed_columns(self) -> tuple[str, ...]:
        """Rule 9: every column a policy reads gets an index. Order is stable so the
        emitter's output is byte-stable."""
        seen: list[str] = []
        for c in (*(self.branch_column(s) for s in self.declared_scopes()),
                  self.soft_delete, *self.parents):
            if c is not None and c not in seen:
                seen.append(c)
        return tuple(seen)


# ── the matrix ──────────────────────────────────────────────────────────────

@dataclass(frozen=True, order=True)
class Grant:
    role: str
    module: str
    action: str
    scope: str


_SCOPE_TOKEN = {"own": "own", "org": "org_subtree", "territory": "territory", "global": "global"}
_ACTION_LETTER = {"C": "create", "E": "edit", "A": "approve", "D": "delete"}
_NOISE = re.compile(r"\*\([^)]*\)\*|\*\*")


def _parse_cell(cell: str, default_scope: str | None) -> tuple[str, list[str]] | None:
    """One matrix cell into (scope, actions), or None for a blank cell.

    Grammar, from RBAC.md section 6: `V:<scope>` then letters from CEAD; portal
    cells write `V` alone and mean partner_subtree; `V + redeem` is view plus
    create (GAP-043); `*(...)*` annotations are UI notes and carry no permission.
    """
    text = _NOISE.sub("", cell).strip()
    if not text:
        return None
    tokens = text.replace("+", " ").split()
    head = tokens[0]
    if head.startswith("V:"):
        scope = _SCOPE_TOKEN[head[2:]]
    elif head == "V":
        if default_scope is None:
            raise ValueError(f"cell {cell!r} has no scope and the table has no default")
        scope = default_scope
    else:
        raise ValueError(f"cell {cell!r} does not start with V")
    actions = ["view"]
    for tok in tokens[1:]:
        if tok == "redeem":
            actions.append("create")
            continue
        for letter in tok:
            if letter not in _ACTION_LETTER:
                raise ValueError(f"cell {cell!r}: unknown action letter {letter!r}")
            actions.append(_ACTION_LETTER[letter])
    return scope, actions


def _tables(markdown: str) -> Iterable[tuple[str, list[str], list[list[str]]]]:
    """Yield (section title, header cells, body rows) for each markdown table
    under a `### 6.n` heading."""
    section = ""
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### 6."):
            section = line[4:].strip()
        if line.startswith("| Module |") and section:
            header = [c.strip() for c in line.strip("|").split("|")]
            i += 2  # the |---| line
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            yield section, header, rows
            continue
        i += 1


def parse_matrix(markdown: str) -> list[Grant]:
    """RBAC.md section 6 into positive permission rows. A blank cell is the absence
    of a row, never a row. The board (6.4) is prose, not a table: view on every
    module at global.

    Enumerated from the document rather than from any seed, so a seed that grants
    a blank cell is caught rather than blessed (FS-002 9.3 A-1).
    """
    grants: list[Grant] = []
    modules: list[str] = []
    for section, header, rows in _tables(markdown):
        default = "partner_subtree" if section.startswith("6.3") else None
        roles = header[1:]
        for row in rows:
            module = row[0]
            if module not in modules:
                modules.append(module)
            for role, cell in zip(roles, row[1:], strict=True):
                parsed = _parse_cell(cell, default)
                if parsed is None:
                    continue
                scope, actions = parsed
                for action in actions:
                    grants.append(Grant(role, module, action, scope))
    if "### 6.4 Board" in markdown:
        grants.extend(Grant("board", m, "view", "global") for m in modules)
    out = sorted(set(grants))
    _check_view_row_rule(out)
    return out


def _check_view_row_rule(grants: Iterable[Grant]) -> None:
    """ISS-029. Every (role, module) with any action has a view row, and one scope."""
    by_pair: dict[tuple[str, str], set[str]] = {}
    scopes: dict[tuple[str, str], set[str]] = {}
    for g in grants:
        by_pair.setdefault((g.role, g.module), set()).add(g.action)
        scopes.setdefault((g.role, g.module), set()).add(g.scope)
    for pair, actions in by_pair.items():
        if "view" not in actions:
            raise ValueError(f"{pair}: actions without a view row")
        if len(scopes[pair]) != 1:
            raise ValueError(f"{pair}: mixed scopes {scopes[pair]}")


def roles_in(grants: Iterable[Grant]) -> tuple[str, ...]:
    return tuple(sorted({g.role for g in grants}))


def modules_in(grants: Iterable[Grant]) -> tuple[str, ...]:
    return tuple(sorted({g.module for g in grants}))


def all_cells(grants: Iterable[Grant]) -> set[tuple[str, str, str]]:
    """Every (role, module, action) the matrix can express: roles x modules x actions."""
    gs = list(grants)
    return {(r, m, a) for r in roles_in(gs) for m in modules_in(gs) for a in ACTIONS}


def denied_cells(grants: Iterable[Grant]) -> set[tuple[str, str, str]]:
    """The cells that matter: everything the matrix does not grant."""
    gs = list(grants)
    return all_cells(gs) - {(g.role, g.module, g.action) for g in gs}
