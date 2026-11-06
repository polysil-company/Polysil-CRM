-- FS-085 rule 11. Where each active staff member's work sits: one row per person,
-- area and kind of evidence. Read only. Feeds `load_district_offices.py sheet`.
-- Run on the box by `deploy_staging.py staff-facts`, wrapped in COPY ... TO STDOUT.
--
-- A territory below a district rolls up to that district. A state-level territory
-- stays at its state, with no district. A person with no evidence gets one row,
-- kind 'none', so everyone is on the sheet.
--
-- kinds: lead_owned, lead_created (created, owned by someone else), lead_dealer (the
-- dealer on a lead they own), order_owned, visit (a partner visited), dealer_created,
-- user_territory (an area they hold).
WITH staff AS (
    SELECT u.id, u.full_name, u.email::text AS email, r.code::text AS role_code,
           r.level AS role_level, r.is_functional, o.id AS office_id, o.name AS office_name,
           ot.name AS office_territory
      FROM app_user u
      JOIN role r ON r.id = u.role_id
      LEFT JOIN org_unit o ON o.id = u.org_unit_id
      LEFT JOIN territory ot ON ot.id = o.territory_id
     WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
       -- the system and intake service accounts (005, 015)
       AND u.id NOT IN ('26809c63-290b-5bd9-9d6a-a717dc0b32e3',
                        '3f962ae5-f0d3-5583-91b5-5cea037139fc')
), evidence AS (
    SELECT l.owner_user_id AS user_id, 'lead_owned' AS kind, l.territory_id
      FROM lead l WHERE l.owner_user_id IS NOT NULL AND l.deleted_at IS NULL
    UNION ALL
    SELECT l.created_by, 'lead_created', l.territory_id
      FROM lead l
     WHERE l.created_by IS NOT NULL AND l.created_by IS DISTINCT FROM l.owner_user_id
       AND l.deleted_at IS NULL
    UNION ALL
    SELECT l.owner_user_id, 'lead_dealer', p.territory_id
      FROM lead l JOIN channel_partner p ON p.id = l.assigned_partner_id
     WHERE l.owner_user_id IS NOT NULL AND l.deleted_at IS NULL
    UNION ALL
    SELECT o.owner_user_id, 'order_owned', coalesce(o.territory_id, p.territory_id)
      FROM sales_order o LEFT JOIN channel_partner p ON p.id = o.partner_id
     WHERE o.owner_user_id IS NOT NULL
    UNION ALL
    SELECT v.user_id, 'visit', p.territory_id
      FROM visit v JOIN channel_partner p ON p.id = v.partner_id
    UNION ALL
    SELECT p.created_by, 'dealer_created', p.territory_id
      FROM channel_partner p WHERE p.created_by IS NOT NULL AND p.deleted_at IS NULL
    UNION ALL
    SELECT ut.user_id, 'user_territory', ut.territory_id FROM user_territory ut
), placed AS (
    SELECT e.user_id, e.kind,
           (SELECT a.id FROM territory_closure tc JOIN territory a ON a.id = tc.ancestor_id
             WHERE tc.descendant_id = e.territory_id AND a.level = 'district'
             ORDER BY tc.depth LIMIT 1) AS district_id,
           (SELECT a.id FROM territory_closure tc JOIN territory a ON a.id = tc.ancestor_id
             WHERE tc.descendant_id = e.territory_id AND a.level = 'state'
             ORDER BY tc.depth LIMIT 1) AS state_id
      FROM evidence e JOIN staff s ON s.id = e.user_id
), counted AS (
    SELECT user_id, kind, state_id, district_id, count(*) AS n
      FROM placed GROUP BY 1, 2, 3, 4
)
SELECT s.id AS user_id, s.full_name, s.email, s.role_code, s.role_level, s.is_functional,
       s.office_id, s.office_name, s.office_territory,
       coalesce(c.kind, 'none') AS kind, st.code::text AS state_code, st.name AS state_name,
       c.district_id, d.name AS district_name, coalesce(c.n, 0) AS n,
       -- live dealers at or under the district: a Field Officer holding several
       -- districts sits in the one with most (FS-085 rule 13)
       (SELECT count(*) FROM channel_partner p
          JOIN territory_closure tc ON tc.descendant_id = p.territory_id
         WHERE tc.ancestor_id = c.district_id AND p.deleted_at IS NULL) AS district_dealers
  FROM staff s
  LEFT JOIN counted c ON c.user_id = s.id
  LEFT JOIN territory st ON st.id = c.state_id
  LEFT JOIN territory d ON d.id = c.district_id
 ORDER BY s.role_level DESC, s.full_name, s.id, kind, st.code, d.name
