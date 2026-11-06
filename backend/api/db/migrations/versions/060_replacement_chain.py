"""060: the replacement order's approval chain (FS-049, client sheet item 12).

A replacement order went to the Dispatch Manager alone (FS-015b D3). It now goes to
the roles in `replacement_approval_roles` (default State Manager, Regional
Manager, MD/CEO), in that order, then Dispatch. `complaint_remedy_replacement` is
rebuilt from 026's text by anchored replacements; the final text is
`COMPLAINT_REMEDY_REPLACEMENT_060`.

Revision ID: 060_replacement_chain
Revises: 058_group_chat
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "060_replacement_chain"
down_revision: str | None = "058_group_chat"
branch_labels = None
depends_on = None


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_060", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"060: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"060: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _or_replace(text: str) -> str:
    return text.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)


BEFORE: str = _or_replace(next(t for t in _load("026_complaint_remedies").FUNCTIONS
                               if re.search(r"FUNCTION\s+complaint_remedy_replacement\(", t)))


def _after() -> str:
    f = BEFORE
    f = _replace(f, "    v_role uuid; v_request uuid; v_remedy uuid; v_total numeric;\n",
                 "    v_role uuid; v_request uuid; v_remedy uuid; v_total numeric;\n"
                 "    v_chain uuid[]; v_bad text; v_seq int := 0; v_step uuid;\n")
    f = _replace(f, """    SELECT id INTO v_role FROM role WHERE code = 'dispatch_manager' AND deleted_at IS NULL;
    IF v_role IS NULL OR NOT EXISTS (SELECT 1 FROM app_user WHERE role_id = v_role AND is_active AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'no active user holds dispatch_manager' USING ERRCODE = 'ORDNA';
    END IF;
""", """    SELECT id INTO v_role FROM role WHERE code = 'dispatch_manager' AND deleted_at IS NULL;
    IF v_role IS NULL OR NOT EXISTS (SELECT 1 FROM app_user WHERE role_id = v_role AND is_active AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'no active user holds dispatch_manager' USING ERRCODE = 'ORDNA';
    END IF;
    -- FS-049: the roles before Dispatch, in the setting's order, each once. Only a
    -- staff line role that approves orders and has an active holder can be a step
    -- (plan review B-1): the setting's trigger checks only that a code exists.
    WITH listed AS (
        SELECT x.code, min(x.ord) AS ord
          FROM jsonb_array_elements_text(coalesce(app_setting_json('replacement_approval_roles'), '[]'::jsonb))
               WITH ORDINALITY AS x(code, ord)
         WHERE x.code <> 'dispatch_manager'
         GROUP BY x.code)
    SELECT string_agg(l.code, ', ') FILTER (WHERE r.id IS NULL OR r.is_functional OR r.is_portal
               OR NOT EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id
                                 AND rp.module = 'sales_orders' AND rp.action = 'approve' AND rp.deleted_at IS NULL)
               OR NOT EXISTS (SELECT 1 FROM app_user u WHERE u.role_id = r.id AND u.is_active AND u.deleted_at IS NULL)),
           array_agg(r.id ORDER BY l.ord)
      INTO v_bad, v_chain
      FROM listed l LEFT JOIN role r ON r.code = l.code AND r.deleted_at IS NULL;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION 'nobody can approve a replacement as %', v_bad USING ERRCODE = 'ORDNA';
    END IF;
""")
    f = _replace(f, """    INSERT INTO approval_step (request_id, seq, approver_role_id) VALUES (v_request, 1, v_role);
""", """    FOREACH v_step IN ARRAY coalesce(v_chain, '{}') LOOP
        v_seq := v_seq + 1;
        INSERT INTO approval_step (request_id, seq, approver_role_id) VALUES (v_request, v_seq, v_step);
    END LOOP;
    INSERT INTO approval_step (request_id, seq, approver_role_id) VALUES (v_request, v_seq + 1, v_role);
""")
    return f


COMPLAINT_REMEDY_REPLACEMENT_060: str = _after()

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('replacement_approval_roles', 'roles', '["state_manager", "regional_manager", "md_ceo"]', NULL, NULL, NULL,
 'Who approves a replacement order, in order, before the Dispatch Manager. Each must be a manager who approves orders.')
ON CONFLICT (key) DO NOTHING"""


def upgrade() -> None:
    op.execute(SEED)
    op.execute(COMPLAINT_REMEDY_REPLACEMENT_060)


def downgrade() -> None:
    op.execute(BEFORE)
    op.execute("DELETE FROM activity_event WHERE kind = 'setting.changed' "
               "AND payload->>'key' = 'replacement_approval_roles'")
    op.execute("DELETE FROM app_setting WHERE key = 'replacement_approval_roles'")
