#!/usr/bin/env python3
"""Generate docs/codebase-graph.md - a navigable map of the backend.

Run after any structural change: new module, table, endpoint, or changed
dependency. Cheap to run, and it is what makes a cold session productive.

    python scripts/generate_graph.py

Never hand-edit the output.
"""
from __future__ import annotations

import ast
import datetime as dt
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "codebase-graph.md"
# Any router variable: leads mounts `lookups`, users `roles`, masters three of
# its own. Matching `@router.` alone hid every one of those endpoints.
ROUTE_RE = re.compile(r'@\w+\.(get|post|patch|put|delete)\(\s*["\']([^"\']*)')


def py_files(*roots: str) -> list[Path]:
    out: list[Path] = []
    for r in roots:
        base = ROOT / r
        if base.exists():
            out += [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(out)


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def parse(p: Path) -> ast.Module | None:
    try:
        return ast.parse(p.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def internal_imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"api", "worker", "domain"}:
                found.add(node.module)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in {"api", "worker", "domain"}:
                    found.add(a.name)
    return found


def public_defs(tree: ast.Module) -> list[str]:
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                out.append(node.name)
    return out


def _dsn() -> dict | None:
    """The same PgBouncer connection everything else uses, if it is reachable."""
    envfile = ROOT / "infra" / ".env"
    if not envfile.exists():
        return None
    env: dict[str, str] = {}
    for line in envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    if not all(env.get(k) for k in ("DB_USER", "DB_PASSWORD", "DB_NAME")):
        return None
    return dict(host="127.0.0.1", port=int(env.get("PGBOUNCER_PORT", "6432")), user=env["DB_USER"],
                password=env["DB_PASSWORD"], dbname=env["DB_NAME"], connect_timeout=4)


def sql_from_database() -> tuple[list[str], dict[str, list[str]], list[tuple[str, str, str]],
                                 list[tuple[str, str]]] | None:
    """Tables, policies, functions and triggers, read from the live schema.

    Source parsing is what this used to do, and it silently under-reports: both
    closure tables are created in a loop in migration 002, so `CREATE TABLE
    {closure}` never matched and the graph claimed 12 tables where there were 14.
    A map that is quietly incomplete is worse than no map, and the database is the
    only source of truth that cannot drift from itself.

    Returns None when the database is not reachable, so the generator still works
    on a machine with no stack up - it just falls back to the old parse.
    """
    kw = _dsn()
    if kw is None:
        return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        with psycopg.connect(**kw) as c:
            cur = c.cursor()
            cur.execute("""
                SELECT c.relname, c.relrowsecurity
                  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public' AND c.relkind = 'r'
                   AND c.relname <> 'alembic_version'
                 ORDER BY c.relname
            """)
            tables = [r[0] for r in cur.fetchall()]

            policies: dict[str, list[str]] = defaultdict(list)
            cur.execute("SELECT tablename, policyname FROM pg_policies "
                        "WHERE schemaname = 'public' ORDER BY tablename, policyname")
            for tbl, pol in cur.fetchall():
                policies[tbl].append(pol)

            # SECURITY DEFINER is the column that matters here: those functions are
            # the authorization surface, and RBAC.md 5.2a is about exactly this set.
            cur.execute("""
                SELECT p.proname,
                       pg_get_function_identity_arguments(p.oid),
                       CASE WHEN p.prosecdef THEN 'definer' ELSE 'invoker' END
                  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                  LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e'
                 WHERE n.nspname = 'public' AND d.objid IS NULL
                 ORDER BY p.proname
            """)
            functions = [tuple(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT c.relname, t.tgname
                  FROM pg_trigger t
                  JOIN pg_class c ON c.oid = t.tgrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public' AND NOT t.tgisinternal
                 ORDER BY c.relname, t.tgname
            """)
            triggers = [tuple(r) for r in cur.fetchall()]
        return tables, policies, functions, triggers
    except Exception:
        return None


def sql_objects() -> tuple[list[str], dict[str, list[str]]]:
    """Fallback: tables and RLS policies parsed from the migrations.

    Only used when the database is unreachable. It under-reports anything created
    in a loop - see sql_from_database.
    """
    tables: list[str] = []
    policies: dict[str, list[str]] = defaultdict(list)
    mig = ROOT / "api" / "db" / "migrations"
    if not mig.exists():
        return tables, policies
    for p in sorted(mig.rglob("*.py")) + sorted(mig.rglob("*.sql")):
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        tables += re.findall(r'create_table\(\s*["\'](\w+)', txt)
        tables += re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", txt, re.I)
        for pol, tbl in re.findall(r"CREATE POLICY (\w+) ON (\w+)", txt, re.I):
            policies[tbl].append(pol)
    return sorted(set(tables)), policies


def section(title: str) -> str:
    return f"\n## {title}\n\n"


def main() -> None:
    files = py_files("api", "worker")
    parsed = {p: t for p in files if (t := parse(p))}

    lines: list[str] = [
        "# Codebase graph",
        "",
        "> **Generated** by `scripts/generate_graph.py`. Never hand-edit.",
        f"> Last generated: {dt.date.today().isoformat()}",
        "",
        "A map of the backend so an agent can find its way without reading everything.",
        "",
    ]

    if not parsed:
        lines += [
            "**No Python source yet.** Run this again once `api/` exists.",
            "",
            "Planned layout is in `docs/architecture/Proposed-Backend-Architecture.md` §2.",
            "",
        ]
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print(f"wrote {rel(OUT)} (no source yet)")
        return

    # --- layers -----------------------------------------------------------
    layers: dict[str, list[Path]] = defaultdict(list)
    for p in parsed:
        parts = p.relative_to(ROOT).parts
        layers[parts[1] if len(parts) > 2 else parts[0]].append(p)

    lines += [section("Layers").rstrip(), ""]
    lines += ["| Layer | Files | Purpose |", "|---|---|---|"]
    purpose = {
        "domain": "pure logic, no I/O, no SQLAlchemy",
        "models": "SQLAlchemy ORM",
        "schemas": "Pydantic, the OpenAPI surface",
        "services": "orchestration, transactions, events",
        "routers": "thin HTTP layer",
        "integrations": "external providers behind protocols",
        "db": "session, RLS helpers, migrations",
        "jobs": "ARQ worker jobs",
    }
    for layer in sorted(layers):
        lines.append(f"| `{layer}` | {len(layers[layer])} | {purpose.get(layer, '')} |")

    # --- endpoints --------------------------------------------------------
    endpoints: list[tuple[str, str, str]] = []
    for p in parsed:
        if "routers" not in p.parts:
            continue
        for m, path in ROUTE_RE.findall(p.read_text(encoding="utf-8")):
            endpoints.append((m.upper(), path, rel(p)))
    if endpoints:
        lines += [section("Endpoints").rstrip(), ""]
        lines += ["| Method | Path | File |", "|---|---|---|"]
        for m, path, f in sorted(endpoints, key=lambda x: (x[1], x[0])):
            lines.append(f"| {m} | `{path}` | `{f}` |")

    # --- domain functions -------------------------------------------------
    dom = [(rel(p), public_defs(t)) for p, t in parsed.items() if "domain" in p.parts]
    dom = [(f, d) for f, d in dom if d]
    if dom:
        lines += [section("Domain functions").rstrip(), "", "Pure. Test these first; they need no database.", ""]
        for f, defs in sorted(dom):
            lines.append(f"- `{f}` — {', '.join(f'`{d}`' for d in defs)}")

    # --- services ---------------------------------------------------------
    svc = [(rel(p), public_defs(t)) for p, t in parsed.items() if "services" in p.parts]
    svc = [(f, d) for f, d in svc if d]
    if svc:
        lines += [section("Services").rstrip(), ""]
        for f, defs in sorted(svc):
            lines.append(f"- `{f}` — {', '.join(f'`{d}`' for d in defs)}")

    # --- dependencies -----------------------------------------------------
    deps: dict[str, set[str]] = {}
    for p, t in parsed.items():
        imp = internal_imports(t)
        if imp:
            deps[rel(p)] = imp
    if deps:
        lines += [section("Module dependencies").rstrip(), "", "```mermaid", "graph LR"]
        seen: set[tuple[str, str]] = set()
        for f, imports in sorted(deps.items()):
            src = f.replace("/", "_").replace(".py", "")
            for i in sorted(imports):
                tgt = i.replace(".", "_")
                if (src, tgt) not in seen:
                    seen.add((src, tgt))
                    lines.append(f"    {src} --> {tgt}")
        lines.append("```")

    # --- tables and RLS ---------------------------------------------------
    live = sql_from_database()
    functions: list[tuple[str, str, str]] = []
    triggers: list[tuple[str, str]] = []
    if live is not None:
        tables, policies, functions, triggers = live
        source = "the live schema"
    else:
        tables, policies = sql_objects()
        source = "the migration source (database unreachable, so this may under-report)"
    if tables:
        lines += [section("Tables").rstrip(), "",
                  f"{len(tables)} tables, read from {source}.", ""]
        lines += ["| Table | RLS policies |", "|---|---|"]
        for t in tables:
            pols = ", ".join(f"`{x}`" for x in policies.get(t, [])) or "**none**"
            lines.append(f"| `{t}` | {pols} |")
        missing = [t for t in tables if not policies.get(t)]
        if missing:
            lines += [
                "",
                f"> **{len(missing)} tables have no RLS policy.** Intentional for lookups and "
                "append-only logs; anything scoped needs one. Check: "
                + ", ".join(f"`{t}`" for t in missing[:20]),
                "",
            ]

    # --- database functions and triggers ----------------------------------
    if functions:
        definer = [f for f in functions if f[2] == "definer"]
        lines += [section("Database functions").rstrip(), "",
                  f"{len(functions)} functions, {len(definer)} of them "
                  "`SECURITY DEFINER`. A definer function runs as its owner, so it "
                  "is authorization surface: `RBAC.md` §5.2a and FS-001 §5.1 are "
                  "about this list.", ""]
        lines += ["| Function | Arguments | Security |", "|---|---|---|"]
        for name, args, sec in functions:
            mark = "**definer**" if sec == "definer" else "invoker"
            lines.append(f"| `{name}` | `{args or ''}` | {mark} |")

    if triggers:
        by_table: dict[str, list[str]] = defaultdict(list)
        for tbl, trg in triggers:
            by_table[tbl].append(trg)
        lines += [section("Triggers").rstrip(), "",
                  f"{len(triggers)} triggers on {len(by_table)} tables. Audit rows, "
                  "closure maintenance and `updated_at` are all trigger-driven, so a "
                  "table missing one here is a table that silently stops being "
                  "audited or maintained.", ""]
        lines += ["| Table | Triggers |", "|---|---|"]
        for tbl in sorted(by_table):
            lines.append(f"| `{tbl}` | " + ", ".join(f"`{t}`" for t in by_table[tbl]) + " |")

    # --- rule violations --------------------------------------------------
    violations: list[str] = []
    for p, t in parsed.items():
        r = rel(p)
        if "domain" in p.parts:
            for node in ast.walk(t):
                mod = getattr(node, "module", None) or ""
                names = [a.name for a in getattr(node, "names", [])]
                if "sqlalchemy" in mod or any("sqlalchemy" in n for n in names):
                    violations.append(f"`{r}` — **domain/ imports SQLAlchemy** (CLAUDE.md §4.1 rule 1)")
                    break
        txt = p.read_text(encoding="utf-8")
        if "SessionLocal(" in txt and not r.endswith("deps.py") and "worker/" not in r:
            violations.append(f"`{r}` — **creates a session outside deps.py** (rule 2)")
        if "services" in p.parts and re.search(r"\.commit\(\)", txt):
            violations.append(f"`{r}` — **service commits** (rule 3)")
    lines += [section("Rule check").rstrip(), ""]
    lines += ([f"- {v}" for v in violations] if violations
              else ["No violations of the automated non-negotiables detected."])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {rel(OUT)} — {len(parsed)} files, {len(endpoints)} endpoints, "
          f"{len(tables)} tables, {len(violations)} violations")


if __name__ == "__main__":
    main()
