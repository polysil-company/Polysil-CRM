"""076: what the client's quotation sheet prints beside the figures (FS-064).

- `quotation_print_block(uuid)`: the dealer, the lead's village, taluka, district
  and state, the place of supply's state, the system and the maker's name. A
  definer guarded on the system principal and granted to nobody: only the render
  claim calls it, as the owner. No approver: a partner never learns who approved
  (FS-012 rules 2 and 9, GAP-493).
- `quotation_render_claim(interval)` carries it as `print`. Three anchors, each
  found exactly once and each reversed on the way down. The call sits in a
  sub-block of its own: a block that raises returns `{"error": ...}` and leaves
  the lease and the attempt charge standing. Without that, one bad row rolls its
  own charge back and is claimed again on every tick, ahead of everything else.

Every sub-select in the block is total. A place name comes from the closure
table, nearest ancestor first, one row; nothing walks `parent_id`.

Revision ID: 076_quotation_print_block
Revises: 075_ap_subsidy
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "076_quotation_print_block"
down_revision: str | None = "075_ap_subsidy"
branch_labels = None
depends_on = None

BLOCK_SIG = "quotation_print_block(uuid)"
CLAIM_SIG = "quotation_render_claim"


def _ancestor(level: str) -> str:
    return (f"(SELECT t.name FROM territory_closure c JOIN territory t ON t.id = c.ancestor_id "
            f"WHERE c.descendant_id = l.territory_id AND t.level = '{level}' "
            f"ORDER BY c.depth LIMIT 1)")


BLOCK = f"""CREATE FUNCTION quotation_print_block(p_quotation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE q quotation%ROWTYPE; l lead%ROWTYPE;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO q FROM quotation WHERE id = p_quotation;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    SELECT * INTO l FROM lead WHERE id = q.lead_id;
    RETURN jsonb_build_object(
        -- the quotation's own dealer, not the lead's: a sent quotation keeps the
        -- dealer it was sent with, and a dealer since closed still prints
        'dealer_name', (SELECT p.name FROM channel_partner p WHERE p.id = q.partner_id),
        'dealer_contact', (SELECT p.contact_name FROM channel_partner p WHERE p.id = q.partner_id),
        'dealer_mobile', (SELECT p.mobile FROM channel_partner p WHERE p.id = q.partner_id),
        -- a village-level territory outranks the free text typed on the lead
        'village', COALESCE({_ancestor('village')}, NULLIF(btrim(l.village), '')),
        'taluka', {_ancestor('taluka')},
        'district', {_ancestor('district')},
        'state', {_ancestor('state')},
        'supply_state', (SELECT t.name FROM territory t WHERE t.id = q.place_of_supply_state_id),
        'mis_system', (SELECT m.name FROM mis_system m WHERE m.id = l.mis_system_id),
        'made_by', (SELECT u.full_name FROM app_user u WHERE u.id = q.created_by));
END $fn$"""

# (old, new) in the claim's body. None is 072's `'quotation', to_jsonb(q)` line,
# so 072's downgrade still finds its own text with 076 applied or not.
SWAPS: tuple[tuple[str, str], ...] = (
    ("DECLARE q quotation%ROWTYPE; v_token uuid;",
     "DECLARE q quotation%ROWTYPE; v_token uuid; v_print jsonb;"),
    ("    RETURN jsonb_build_object(\n        'lease_token', v_token,",
     "    BEGIN\n"
     "        v_print := quotation_print_block(q.id);\n"
     "    EXCEPTION WHEN OTHERS THEN\n"
     "        v_print := jsonb_build_object('error', SQLERRM);\n"
     "    END;\n"
     "    RETURN jsonb_build_object(\n        'lease_token', v_token,"),
    ("        'lines', (SELECT COALESCE(jsonb_agg(",
     "        'print', v_print,\n        'lines', (SELECT COALESCE(jsonb_agg("),
)


def _swap(pairs: tuple[tuple[str, str], ...]) -> None:
    body = str(op.get_bind().execute(
        text(f"SELECT pg_get_functiondef('{CLAIM_SIG}'::regproc)")).scalar_one())
    for old, new in pairs:
        if body.count(old) != 1:
            raise RuntimeError(
                f"076: {CLAIM_SIG} anchor found {body.count(old)} times: {old[:40]!r}")
        body = body.replace(old, new)
    op.execute(body)


def upgrade() -> None:
    op.execute(BLOCK)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {BLOCK_SIG} FROM PUBLIC")
    _swap(SWAPS)


def downgrade() -> None:
    _swap(tuple((new, old) for old, new in reversed(SWAPS)))
    op.execute(f"DROP FUNCTION IF EXISTS {BLOCK_SIG}")
