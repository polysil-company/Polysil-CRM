"""066: a whole-number setting is stored as a whole number (ISS-129).

`app_setting_check` accepted `1.0` for an int setting, and readers that cast
`(value #>> '{}')::int` (041's complaint reopen) raise on the text '1.0'. The
check now rewrites the value to its integer form, so every reader is safe, and
any row already holding a decimal form is rewritten once.

Revision ID: 066_int_setting_whole
Revises: 065_dealership_inquiry
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "066_int_setting_whole"
down_revision: str | None = "065_dealership_inquiry"
branch_labels = None
depends_on = None


def _051_check() -> str:
    path = Path(__file__).with_name("051_ratings.py")
    spec = importlib.util.spec_from_file_location("mig_051_for_066", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return str(mod.SETTING_CHECK)


BEFORE = _051_check()
_ANCHOR = """        v := (NEW.value #>> '{}')::numeric;
        IF v <> trunc(v) OR (NEW.min IS NOT NULL AND v < NEW.min) OR (NEW.max IS NOT NULL AND v > NEW.max) THEN
            RAISE EXCEPTION 'setting %: % to %', NEW.key, NEW.min, NEW.max USING ERRCODE = 'SETVL';
        END IF;
"""
if BEFORE.count(_ANCHOR) != 1:
    raise RuntimeError("066: anchor not found once in app_setting_check")
AFTER = BEFORE.replace(_ANCHOR, _ANCHOR + """        -- ISS-129: 1.0 is stored as 1, so a reader's ::int cast never meets '1.0'
        NEW.value := to_jsonb(v::bigint);
""")


def upgrade() -> None:
    op.execute(AFTER)
    op.execute("UPDATE app_setting SET value = to_jsonb((value #>> '{}')::numeric::bigint) "
               "WHERE kind = 'int' AND jsonb_typeof(value) = 'number' "
               "AND (value #>> '{}') LIKE '%.%'")


def downgrade() -> None:
    op.execute(BEFORE)
