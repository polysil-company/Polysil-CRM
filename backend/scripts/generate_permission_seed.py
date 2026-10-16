"""The permission rows, from RBAC.md section 6 and nothing else.

    python scripts/generate_permission_seed.py          # SQL, to stdout
    python scripts/generate_permission_seed.py --json   # rows as JSON

Positive rows only: a blank cell in the matrix is the absence of a row (RBAC.md
section 6). The demo seed and migration 005 consume `load_grants()`; the parity
suite enumerates the denied cells from the same source, so a seed that grants a
blank cell is caught rather than blessed (FS-002 9.3 A-1).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.domain.authz import Grant, parse_matrix  # noqa: E402

RBAC = ROOT / "docs" / "architecture" / "RBAC.md"


def load_grants() -> list[Grant]:
    return parse_matrix(RBAC.read_text(encoding="utf-8"))


def as_sql(grants: list[Grant]) -> str:
    lines = ["INSERT INTO role_permission (role_id, module, action, scope)",
             "SELECT r.id, v.module, v.action::permission_action, v.scope::permission_scope",
             "  FROM (VALUES"]
    lines += [f"    ('{g.role}', '{g.module}', '{g.action}', '{g.scope}')," for g in grants]
    lines[-1] = lines[-1].rstrip(",")
    lines += ["  ) AS v(role, module, action, scope)",
              "  JOIN role r ON r.code = v.role",
              "ON CONFLICT (role_id, module, action) DO UPDATE SET scope = EXCLUDED.scope;"]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    grants = load_grants()
    if "--json" in argv:
        print(json.dumps([g.__dict__ for g in grants], indent=1))
    else:
        print(as_sql(grants))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
