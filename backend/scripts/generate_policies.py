"""Emit the RLS policies and indexes for every declared module.

    python scripts/generate_policies.py            # all modules, to stdout
    python scripts/generate_policies.py partners   # one module

The output is pasted into a migration and reviewed by hand; it is never applied
from here. The drift test regenerates it and compares against the live
pg_policies, so a ScopeSpec edited without a migration is a red suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.authz.modules import SPECS
from api.authz.policy_sql import indexes_for, policies_for


def render(module: str) -> str:
    spec = SPECS[module]
    parts = [f"-- {module} over {spec.table}, generated from api/authz/modules.py"]
    parts += [f"{stmt};" for stmt in indexes_for(spec)]
    parts += [f"{stmt};" for stmt in policies_for(spec)]
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    modules = argv[1:] or list(SPECS)
    unknown = [m for m in modules if m not in SPECS]
    if unknown:
        print(f"unknown module(s): {', '.join(unknown)}; declared: {', '.join(SPECS)}",
              file=sys.stderr)
        return 2
    print("\n\n".join(render(m) for m in modules))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
