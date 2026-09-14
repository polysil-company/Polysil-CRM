"""002 hierarchy: territory, org_unit and both closure tables

FS-001 section 5, `Proposed-Schema.md` section 3.

`created_by` and `updated_by` ship as bare `uuid` on both tables. Section 1.2 puts
`created_by references app_user(id)` on every business table, and `app_user` does
not exist until 003, so the constraints are added by ALTER TABLE at the end of 003
(`Schema-Corrections.md` section 5a.6).

The audit triggers for these two tables are also attached at the end of 003, not
here. `audit_row()` calls `app_current_user_id()`, which 003 creates - the plpgsql
body defers, so creating the trigger here would work, but stopping an upgrade at
002 and inserting a territory by hand would then fail with a missing function.
Attaching every audit trigger in one place, after the function exists, removes
that and makes the set reviewable together. `updated_at` has no such dependency
and is attached here with its tables.

Revision ID: 002_hierarchy
Revises: 001_foundation
Created: during development
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "002_hierarchy"
down_revision: str | None = "001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Proposed-Schema.md section 1.2. Repeated rather than generated: a migration is
# read far more often than it is written, and the columns are the shape of the row.
COMMON = """
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid,
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz
"""

# territory and org_unit, and partner_closure will be a third in 004.
TREES = (("territory", "territory_closure"), ("org_unit", "org_closure"))


def upgrade() -> None:
    op.execute("CREATE TYPE territory_level AS ENUM ('state', 'district', 'taluka', 'village')")

    # The CHECK is what stops a node becoming its own parent. Without it the AFTER
    # INSERT trigger below finds no ancestor rows for a self-parented node, writes
    # only the self row, and leaves a tree the closure table quietly disagrees with.
    op.execute(
        f"""
        CREATE TABLE territory (
            id        uuid            PRIMARY KEY DEFAULT gen_random_uuid(),
            parent_id uuid            REFERENCES territory(id),
            level     territory_level NOT NULL,
            name      text            NOT NULL,
            code      citext,
            lgd_code  text,
            {COMMON},
            CONSTRAINT ck_territory_not_own_parent
                CHECK (parent_id IS NULL OR parent_id <> id)
        )
        """
    )
    op.execute("CREATE INDEX ix_territory_parent_level ON territory (parent_id, level)")
    op.execute("CREATE INDEX ix_territory_level_code ON territory (level, code)")
    op.execute(
        "CREATE UNIQUE INDEX uq_territory_external ON territory (source_system, external_id) "
        "WHERE external_id IS NOT NULL"
    )

    op.execute(
        f"""
        CREATE TABLE org_unit (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            parent_id    uuid REFERENCES org_unit(id),
            name         text NOT NULL,
            role_level   int  NOT NULL,
            territory_id uuid REFERENCES territory(id),
            {COMMON},
            CONSTRAINT ck_org_unit_not_own_parent
                CHECK (parent_id IS NULL OR parent_id <> id)
        )
        """
    )
    op.execute("CREATE INDEX ix_org_unit_parent ON org_unit (parent_id)")
    op.execute("CREATE INDEX ix_org_unit_territory ON org_unit (territory_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_org_unit_external ON org_unit (source_system, external_id) "
        "WHERE external_id IS NOT NULL"
    )

    # Both closures are the same shape (Proposed-Schema.md section 3). ON DELETE
    # CASCADE on both columns is what maintains the delete case: deleting a node
    # removes every row naming it as ancestor or descendant, and the self-FK on the
    # node table has no cascade, so a node with children cannot be deleted out from
    # under its subtree.
    #
    # A soft delete is not a delete and does not touch these rows. That is ISS-028,
    # and it is owned by FS-002.
    for node, closure in TREES:
        op.execute(
            f"""
            CREATE TABLE {closure} (
                ancestor_id   uuid NOT NULL REFERENCES {node}(id) ON DELETE CASCADE,
                descendant_id uuid NOT NULL REFERENCES {node}(id) ON DELETE CASCADE,
                depth         int  NOT NULL,
                PRIMARY KEY (ancestor_id, descendant_id)
            )
            """
        )
        # The primary key covers the DOWNWARD walk, and that is the one every RLS
        # policy in RBAC.md section 5 runs: `WHERE ancestor_id = app_current_org_unit()`
        # selecting descendant_id. No policy reads this index.
        #
        # It is still needed, for two other readers. closure_maintain() above looks up
        # `WHERE descendant_id = <parent>` on every insert and every move, so without
        # it a subtree move on a large tree degrades to a scan. And the upward walk -
        # find my ancestors - is what derives lead.senior_manager_id in FS-002.
        op.execute(f"CREATE INDEX ix_{closure}_descendant ON {closure} (descendant_id)")

    # One function for all three closures. The table name comes from TG_ARGV, which
    # is written into the CREATE TRIGGER statements below - it is never caller
    # input - and is passed through quote_ident regardless.
    #
    # Insert and parent change only. Delete is the FK cascade above.
    op.execute(
        """
        CREATE FUNCTION closure_maintain() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE
            t       text := quote_ident(TG_ARGV[0]);
            n       text := quote_ident(TG_TABLE_NAME);
            v_cycle boolean;
        BEGIN
            -- Serialise every mutation of one tree, before anything reads the
            -- closure. Without it two concurrent moves each read the pre-move
            -- closure, so both cycle checks pass and both commit - A under B and B
            -- under A at once. Reproduced through PgBouncer with no error raised
            -- and reciprocal parent pointers left behind (FS-001 9.8 X-4).
            --
            -- Coarse on purpose: one lock per tree, not per subtree. These trees
            -- are org units and territories, written rarely and read constantly,
            -- so correctness is worth more than move concurrency. The two-integer
            -- key form namespaces it against the other advisory lock in this
            -- schema (ISS-042).
            PERFORM pg_advisory_xact_lock(2, hashtext(TG_TABLE_NAME));

            IF TG_OP = 'INSERT' THEN
                -- Ancestry is walked over the NODE table, not over the closure.
                --
                -- The closure is the obvious source and it is wrong here. AFTER
                -- ROW triggers fire in row order, so a multirow INSERT that lists
                -- a child before its parent runs the child's trigger while the
                -- parent has no closure row yet - the lookup finds nothing and the
                -- child silently gets only its self row, losing every ancestor.
                -- The node table does not have that problem: by AFTER ROW time it
                -- holds every row of the statement. A bulk import is exactly the
                -- case that hits this, and it fails silently (FS-001 9.8 X-6).
                --
                -- depth < 64 is a termination guard. The advisory lock above plus
                -- the cycle check below should make a loop impossible; if one ever
                -- existed this would otherwise recurse forever rather than fail.
                EXECUTE format(
                    'INSERT INTO %s (ancestor_id, descendant_id, depth)
                     WITH RECURSIVE up AS (
                         SELECT $1::uuid AS node, 0 AS depth
                         UNION ALL
                         SELECT p.parent_id, up.depth + 1
                           FROM up JOIN %s p ON p.id = up.node
                          WHERE p.parent_id IS NOT NULL AND up.depth < 64
                     )
                     SELECT up.node, $1, up.depth FROM up', t, n)
                    USING NEW.id;
                RETURN NULL;
            END IF;

            -- Parent change. The closure still describes the old tree at this
            -- point, which is what makes the cycle test below meaningful: if the
            -- new parent is already a descendant of this node, the move closes a
            -- loop and the closure stops terminating.
            EXECUTE format(
                'SELECT EXISTS (SELECT 1 FROM %s
                                 WHERE ancestor_id = $1 AND descendant_id = $2)', t)
                INTO v_cycle USING NEW.id, NEW.parent_id;
            IF v_cycle THEN
                RAISE EXCEPTION '% % cannot be moved under its own descendant %',
                    TG_TABLE_NAME, NEW.id, NEW.parent_id USING ERRCODE = '23514';
            END IF;

            -- Cut the subtree loose from everything above it. Rows whose ancestor
            -- is itself inside the subtree stay, and that includes every self row.
            EXECUTE format(
                'DELETE FROM %s
                       WHERE descendant_id IN (SELECT descendant_id FROM %s
                                                WHERE ancestor_id = $1)
                         AND ancestor_id NOT IN (SELECT descendant_id FROM %s
                                                  WHERE ancestor_id = $1)', t, t, t)
                USING NEW.id;

            -- Re-attach it under the new parent: every ancestor of the new parent
            -- crossed with every descendant of the moved node. A NULL parent
            -- matches nothing, so the subtree becomes a root, which is correct.
            EXECUTE format(
                'INSERT INTO %s (ancestor_id, descendant_id, depth)
                      SELECT a.ancestor_id, d.descendant_id, a.depth + d.depth + 1
                        FROM %s a
                        CROSS JOIN %s d
                       WHERE a.descendant_id = $2 AND d.ancestor_id = $1', t, t, t)
                USING NEW.id, NEW.parent_id;

            RETURN NULL;
        END $fn$
        """
    )

    for node, closure in TREES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{node}_closure_insert
                AFTER INSERT ON {node}
                FOR EACH ROW EXECUTE FUNCTION closure_maintain('{closure}')
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{node}_closure_move
                AFTER UPDATE OF parent_id ON {node}
                FOR EACH ROW WHEN (NEW.parent_id IS DISTINCT FROM OLD.parent_id)
                EXECUTE FUNCTION closure_maintain('{closure}')
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{node}_updated_at
                BEFORE UPDATE ON {node}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at()
            """
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS closure_maintain() CASCADE")
    op.execute("DROP TABLE IF EXISTS org_closure")
    op.execute("DROP TABLE IF EXISTS territory_closure")
    op.execute("DROP TABLE IF EXISTS org_unit")
    op.execute("DROP TABLE IF EXISTS territory")
    op.execute("DROP TYPE IF EXISTS territory_level")
