"""004 channel tree: channel_partner and partner_closure

FS-002a. `Proposed-Schema.md` section 4, section 18's `004` line, and the deferred
foreign key `Schema-Corrections.md` 5a.6 assigns here. Pulled forward from W3 so
FS-002's partner_subtree branch has a real closure table to run on.

Four things in here that a reading of the schema document would not give you:

  1. The type-order check is a CONSTRAINT TRIGGER, AFTER, not a BEFORE trigger.
     A BEFORE ROW trigger on a multirow INSERT that lists a child before its parent
     cannot see the parent. 002 documents the same hazard for the closure trigger
     and solves it the same way. Executed: the AFTER form accepts a child-first
     insert and still refuses a sub_dealer under a distributor.

  2. price_tier = partner_type is enforced by a CHECK. Rev 1 said the two "may
     differ" and cited ADR-033, which says nothing about tiers; ADR-030 says tier
     follows type. The CHECK is the reversible default: dropping it is one
     statement, adding it after divergent data exists is not. GAP-037.

  3. The foreign key on app_user.partner_id is added NOT VALID, then validated if
     it can be. Every database that has run seed_demo.py holds a partner_user
     whose partner_id points at nothing, because there was nothing to point at.
     NOT VALID enforces every write from now on and leaves the old row alone;
     seed_demo.py now creates the partner with the id that row already carries,
     so a reseed heals it and the next upgrade validates. CLAUDE.md 4.3's
     add-then-enforce split.

  4. The function created here has EXECUTE revoked from PUBLIC at the end, the
     same block 003a uses. ISS-040: ALTER DEFAULT PRIVILEGES does not do this,
     and a live-schema test fails the suite if any function this project created
     is PUBLIC-executable.

  5. channel_partner has ROW LEVEL SECURITY enabled with no policies. That
     denies everything to a non-owner (FS-002 section 5.2 fact 4), which is the
     right state for a table with no service in front of it: fail closed until
     FS-002's migration adds the policies. Rule 8 (ENABLE and policies in one
     migration) exists to prevent an accidental outage; this is a deliberate
     one on a table nothing reads yet. partner_closure stays RLS-free: FS-002's
     policies read it in a USING subselect as the invoking user.

  6. Three trees now share advisory lock class 2, keyed by table name. A
     transaction that writes two trees must take them in this order:
     territory, org_unit, channel_partner. Executed: two sessions writing
     org_unit and channel_partner in opposite orders deadlock (ISS-054).

Revision ID: 004_channel_tree
Revises: 003b_role_grants
Created: during development
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "004_channel_tree"
down_revision: str | None = "003b_role_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Section 1.2's common columns. app_user exists by now, so created_by and updated_by
# carry their references inline rather than as the ALTER TABLE 003 needed.
COMMON = """
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz
"""

GSTIN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
PAN = r"^[A-Z]{5}[0-9]{4}[A-Z]$"
# Digits only, country code included, no plus sign - the form app_user.mobile and
# the OTP path already use.
MOBILE = r"^[0-9]{10,15}$"


def upgrade() -> None:
    op.execute("CREATE TYPE partner_type AS ENUM ('distributor', 'dealer', 'sub_dealer')")
    # Shared with price_list.channel_tier (Proposed-Schema.md section 7), which W3
    # creates. One enum for both, so a partner's tier and a price list's tier are
    # the same type and cannot drift by spelling.
    op.execute(
        "CREATE TYPE channel_tier AS ENUM ('distributor', 'dealer', 'sub_dealer', 'farmer')"
    )

    op.execute(
        f"""
        CREATE TABLE channel_partner (
            id                 uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
            -- RESTRICT rather than the default NO ACTION, and it buys less than it
            -- reads. Executed: a single-row delete of a parent is refused under
            -- either; a DELETE naming parent and child in one statement removes
            -- both, and their closure rows, under either - RI checks fire at end
            -- of statement in both cases. RESTRICT only forbids deferring the
            -- check. The real guard is that app_role holds no DELETE on this
            -- table (FS-002 5.1). Hard delete is an ops action. ISS-053.
            parent_id          uuid         REFERENCES channel_partner(id) ON DELETE RESTRICT,
            partner_type       partner_type NOT NULL,
            code               citext       NOT NULL,
            name               text         NOT NULL,
            contact_name       text,
            mobile             text,
            email              citext,
            -- NOT NULL from the start. It is the only staff-side scoping column
            -- this table has (GAP-036), and relaxing NOT NULL later is one
            -- statement while adding it later is a backfill.
            territory_id       uuid         NOT NULL REFERENCES territory(id),
            address            text,
            gstin              text,
            pan                text,
            is_gst_registered  boolean      NOT NULL DEFAULT false,
            price_tier         channel_tier NOT NULL,
            credit_limit       numeric(14,2),
            payment_terms_days int,
            is_active          boolean      NOT NULL DEFAULT true,
            {COMMON},
            CONSTRAINT ck_channel_partner_not_own_parent
                CHECK (parent_id IS NULL OR parent_id <> id),
            -- NOT NULL does not exclude ''. citext folds case, not whitespace, so
            -- 'ABC ' and 'ABC' would otherwise be two live dealers.
            CONSTRAINT ck_channel_partner_code_shape
                CHECK (code = btrim(code) AND length(code) BETWEEN 1 AND 32),
            CONSTRAINT ck_channel_partner_name_shape
                CHECK (length(btrim(name)) BETWEEN 1 AND 200),
            CONSTRAINT ck_channel_partner_mobile_format
                CHECK (mobile IS NULL OR mobile ~ '{MOBILE}'),
            CONSTRAINT ck_channel_partner_gstin_format
                CHECK (gstin IS NULL OR gstin ~ '{GSTIN}'),
            CONSTRAINT ck_channel_partner_pan_format
                CHECK (pan IS NULL OR pan ~ '{PAN}'),
            CONSTRAINT ck_channel_partner_gstin_when_registered
                CHECK (NOT is_gst_registered OR gstin IS NOT NULL),
            -- Unreachable while tier_matches_type below exists, since no partner_type
            -- is 'farmer'. Kept on purpose: it is the only guard left the day GAP-037
            -- drops the matching check.
            CONSTRAINT ck_channel_partner_tier_not_farmer
                CHECK (price_tier <> 'farmer'),
            -- GAP-037. Drop this one line if the client says a dealer may sit on
            -- distributor pricing.
            CONSTRAINT ck_channel_partner_tier_matches_type
                CHECK (price_tier::text = partner_type::text),
            CONSTRAINT ck_channel_partner_credit_limit
                CHECK (credit_limit IS NULL OR credit_limit >= 0),
            CONSTRAINT ck_channel_partner_payment_terms
                CHECK (payment_terms_days IS NULL OR payment_terms_days >= 0)
        )
        """
    )
    # Partial, not a table-level UNIQUE: a closed partner's code can be reissued.
    # Schema-Corrections.md 5a.4, the app_user.mobile precedent.
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_partner_code ON channel_partner (code) "
        "WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_partner_external ON channel_partner "
        "(source_system, external_id) WHERE external_id IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_channel_partner_parent ON channel_partner (parent_id)")
    # Rule 9. FS-002's territory branch on this table reads it.
    op.execute("CREATE INDEX ix_channel_partner_territory ON channel_partner (territory_id)")

    # The same shape as org_closure, for the same reasons 002 gives: CASCADE on both
    # columns is the delete case, the primary key covers the downward walk every
    # policy runs, and the descendant index serves closure_maintain()'s own lookup.
    op.execute(
        """
        CREATE TABLE partner_closure (
            ancestor_id   uuid NOT NULL REFERENCES channel_partner(id) ON DELETE CASCADE,
            descendant_id uuid NOT NULL REFERENCES channel_partner(id) ON DELETE CASCADE,
            depth         int  NOT NULL,
            PRIMARY KEY (ancestor_id, descendant_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_partner_closure_descendant ON partner_closure (descendant_id)")

    # The tree is typed: distributor -> dealer -> sub_dealer, one level per edge. A
    # root may be any type (GAP-034). A CHECK cannot read the parent row, so this
    # is a trigger, and it is a CONSTRAINT TRIGGER in AFTER timing so that a
    # multirow INSERT listing a child before its parent can see the parent - see
    # the module docstring. On a type change it also checks the existing children,
    # or a distributor with dealers under it could quietly become a sub_dealer.
    op.execute(
        """
        CREATE FUNCTION channel_partner_type_order() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE
            v_parent_type    partner_type;
            v_parent_deleted timestamptz;
            v_rank_new       int;
            v_rank_parent    int;
            v_bad_child      uuid;
        BEGIN
            -- The same lock closure_maintain() takes for this tree, so a type
            -- check and a closure change serialise together. Without it, a child
            -- insert and a parent retype in two sessions both pass their own
            -- check and commit an illegal edge. Executed (FS-002a EC-5).
            -- Re-entrant within the transaction, so the closure trigger taking it
            -- again is fine.
            PERFORM pg_advisory_xact_lock(2, hashtext('channel_partner'));

            v_rank_new := CASE NEW.partner_type
                              WHEN 'distributor' THEN 1
                              WHEN 'dealer'      THEN 2
                              ELSE 3 END;

            IF NEW.parent_id IS NOT NULL THEN
                SELECT partner_type, deleted_at INTO v_parent_type, v_parent_deleted
                  FROM channel_partner WHERE id = NEW.parent_id
                   FOR KEY SHARE;
                -- A missing parent is the foreign key's error to raise, not ours.
                IF v_parent_type IS NOT NULL THEN
                    -- The half of GAP-031 that needs no client answer: nothing new
                    -- attaches under a closed partner.
                    IF v_parent_deleted IS NOT NULL THEN
                        RAISE EXCEPTION 'parent % is soft-deleted; nothing may attach under it',
                            NEW.parent_id USING ERRCODE = '23514';
                    END IF;
                    v_rank_parent := CASE v_parent_type
                                         WHEN 'distributor' THEN 1
                                         WHEN 'dealer'      THEN 2
                                         ELSE 3 END;
                    IF v_rank_new <> v_rank_parent + 1 THEN
                        RAISE EXCEPTION
                            'a % cannot sit under a %; '
                            'the order is distributor > dealer > sub_dealer',
                            NEW.partner_type, v_parent_type
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
            END IF;

            IF TG_OP = 'UPDATE' AND NEW.partner_type IS DISTINCT FROM OLD.partner_type THEN
                SELECT c.id INTO v_bad_child
                  FROM channel_partner c
                 WHERE c.parent_id = NEW.id
                   AND (CASE c.partner_type
                            WHEN 'distributor' THEN 1
                            WHEN 'dealer'      THEN 2
                            ELSE 3 END) <> v_rank_new + 1
                 LIMIT 1;
                IF v_bad_child IS NOT NULL THEN
                    RAISE EXCEPTION
                        '% cannot become a %: child % would no longer fit under it',
                        NEW.id, NEW.partner_type, v_bad_child
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_channel_partner_type_order
            AFTER INSERT OR UPDATE OF parent_id, partner_type ON channel_partner
            DEFERRABLE INITIALLY IMMEDIATE
            FOR EACH ROW EXECUTE FUNCTION channel_partner_type_order()
        """
    )

    # 002's closure_maintain(), unchanged. It takes the closure name through
    # TG_ARGV[0], and its advisory lock is keyed on TG_TABLE_NAME, so a third tree
    # namespaces itself.
    op.execute(
        """
        CREATE TRIGGER trg_channel_partner_closure_insert
            AFTER INSERT ON channel_partner
            FOR EACH ROW EXECUTE FUNCTION closure_maintain('partner_closure')
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_channel_partner_closure_move
            AFTER UPDATE OF parent_id ON channel_partner
            FOR EACH ROW WHEN (NEW.parent_id IS DISTINCT FROM OLD.parent_id)
            EXECUTE FUNCTION closure_maintain('partner_closure')
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_channel_partner_updated_at
            BEFORE UPDATE ON channel_partner
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_channel_partner_audit
            AFTER INSERT OR UPDATE OR DELETE ON channel_partner
            FOR EACH ROW EXECUTE FUNCTION audit_row()
        """
    )

    # Fail closed until FS-002 adds the policies. See the module docstring, item 5.
    # No effect on the owner, which is what every test and the seed run as today;
    # total denial for app_role, which holds no grant on this table yet anyway.
    op.execute("ALTER TABLE channel_partner ENABLE ROW LEVEL SECURITY")

    # The forward reference 003 left bare. NOT VALID: see the module docstring.
    op.execute(
        """
        ALTER TABLE app_user
            ADD CONSTRAINT fk_app_user_partner_id
            FOREIGN KEY (partner_id) REFERENCES channel_partner(id) NOT VALID
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE app_user VALIDATE CONSTRAINT fk_app_user_partner_id;
        EXCEPTION WHEN foreign_key_violation THEN
            RAISE NOTICE 'fk_app_user_partner_id left NOT VALID: a partner_user points at '
                         'no channel_partner. Run scripts/seed_demo.py, which creates the '
                         'demo partner under that id and validates the constraint. '
                         'New writes are enforced regardless.';
        END $$
        """
    )

    # The function above is PUBLIC-executable until this runs (ISS-040). The blanket
    # revoke does not disturb app_anon's direct grants; 003a is the precedent.
    op.execute(
        """
        DO $$
        DECLARE v_public int;
        BEGIN
            REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
            SELECT count(*) INTO v_public
              FROM pg_proc p
              JOIN pg_namespace n ON n.oid = p.pronamespace
              LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e'
             WHERE n.nspname = 'public' AND d.objid IS NULL
               AND has_function_privilege('public', p.oid, 'EXECUTE');
            IF v_public > 0 THEN
                RAISE EXCEPTION
                    '% functions in public are still executable by PUBLIC', v_public;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    # channel_tier becomes shared with price_list from W3's migration on. Downgrading
    # this revision past that one is not a thing; that migration's downgrade has to
    # run first, which Alembic's ordering guarantees.
    op.execute("ALTER TABLE app_user DROP CONSTRAINT IF EXISTS fk_app_user_partner_id")
    for trg in ("audit", "updated_at", "closure_move", "closure_insert", "type_order"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_channel_partner_{trg} ON channel_partner")
    op.execute("DROP FUNCTION IF EXISTS channel_partner_type_order()")
    op.execute("DROP TABLE IF EXISTS partner_closure")
    op.execute("DROP TABLE IF EXISTS channel_partner")
    op.execute("DROP TYPE IF EXISTS channel_tier")
    op.execute("DROP TYPE IF EXISTS partner_type")
