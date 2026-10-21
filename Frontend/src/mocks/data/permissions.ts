import {
  MODULE_CODES,
  PERMISSION_ACTIONS,
  type ModuleCode,
  type PermissionAction,
} from "@/lib/auth/permissions";
import type { Role } from "@/lib/auth/roles";

/**
 * What GET /auth/me returns as `permissions` for each role, in the mock backend.
 *
 * The real matrix lives in the backend's database. This one follows the rules
 * agreed with the client (Docs/Frontend-Scope.md §4), so every role can be previewed:
 *  - Marketing offers are for channel partners; only Admin manages them.
 *  - Schemes are visible to everyone; only Admin manages them.
 *  - Accounts, Dispatch and QA are single-person queues focused on their own work.
 *  - Managers approve; employees do not.
 *
 * TODO(AUTH-002): replace with the backend's seeded matrix once RBAC.md is shared.
 */

type Scope = "own" | "org_subtree" | "territory" | "partner_subtree" | "global";

export interface MockModulePermission {
  module: ModuleCode;
  actions: PermissionAction[];
  scope: Scope | null;
}

function grant(
  module: ModuleCode,
  actions: readonly PermissionAction[],
  scope: Scope,
): MockModulePermission {
  return { module, actions: [...actions], scope };
}

const SCHEMES_VIEW = grant("schemes", ["view"], "global");
/** Everyone reads the catalogue and the prices of their tier; Admin alone edits (RBAC.md §6). */
const CATALOGUE_VIEW = [
  grant("products", ["view"], "global"),
  grant("pricing", ["view"], "global"),
];

/** Every staff role reads stock; dealers see none (stock contract). */
const STOCK_VIEW = grant("stock", ["view"], "global");

function fieldStaff(scope: Scope): MockModulePermission[] {
  return [
    grant("leads", ["view", "create", "edit"], scope),
    grant("quotations", ["view", "create", "edit"], scope),
    grant("sales_orders", ["view", "create", "edit"], scope),
    grant("subsidy", ["view", "create"], scope),
    grant("complaints", ["view", "create"], scope),
    // Field tracking (migration 030): staff track themselves; view reaches by scope.
    grant("tracking", ["view", "create"], scope),
    grant("tasks", ["view", "create", "edit"], scope),
    grant("partners", ["view"], scope),
    // Officers see their own targets; managers set them for their team (migration 035).
    grant("targets", ["view"], scope),
    // RBAC.md §6.1: rewards V:own for a field officer, V:org for managers.
    grant("rewards", ["view"], scope),
    STOCK_VIEW,
    // Marketing material: anyone orders for a dealer or their office (handover).
    grant("marketing_material", ["view", "create"], scope),
    SCHEMES_VIEW,
    ...CATALOGUE_VIEW,
  ];
}

function manager(scope: Scope): MockModulePermission[] {
  return [
    // One entry per module, as GET /auth/me returns: the manager's replace the officer's.
    ...fieldStaff(scope).filter(
      (entry) =>
        entry.module !== "quotations" &&
        entry.module !== "sales_orders" &&
        entry.module !== "complaints" &&
        entry.module !== "partners" &&
        entry.module !== "targets" &&
        entry.module !== "marketing_material",
    ),
    // The District Manager over the office approves marketing material (handover).
    grant("marketing_material", ["view", "create", "approve"], scope),
    // Managers see their team's targets and set them for the people below them.
    grant("targets", ["view", "create"], scope),
    // District and State Managers add and correct partners in their area (RBAC.md §6.1).
    grant("partners", ["view", "create", "edit"], scope),
    // Managers check complaints before QC (RBAC.md §6.1: complaints CEA).
    grant("complaints", ["view", "create", "edit", "approve"], scope),
    // Managers approve orders and quotation discounts (RBAC.md §6.1).
    grant("quotations", ["view", "create", "edit", "approve"], scope),
    grant("sales_orders", ["view", "create", "edit", "approve"], scope),
    grant("reports", ["view"], scope),
  ];
}

/** No `subsidy`: the backend answers portal users 403 there (handover `subsidy-calculation.md`). */
function channelPartner(role: "distributor" | "dealer" | "sub_dealer"): MockModulePermission[] {
  return [
    // RBAC.md §6.3: a distributor or dealer views, adds and corrects the next type down
    // under itself (CHNL-002, decided by the client on 20 Oct); a sub-dealer has none.
    ...(role === "sub_dealer"
      ? []
      : [grant("partners", ["view", "create", "edit"], "partner_subtree")]),
    grant("leads", ["view", "edit"], "partner_subtree"),
    grant("sales_orders", ["view", "create", "edit"], "partner_subtree"),
    grant("complaints", ["view", "create"], "partner_subtree"),
    grant("marketing", ["view"], "global"),
    // A dealer orders marketing material for itself (handover).
    grant("marketing_material", ["view", "create"], "partner_subtree"),
    // RBAC.md §6.3: "V + redeem", view and create (GAP-043).
    grant("rewards", ["view", "create"], "partner_subtree"),
    // RBAC.md §6.3: their own tasks, completed, while `tasks_for_dealers` is on (FS-037).
    grant("tasks", ["view", "edit"], "own"),
    SCHEMES_VIEW,
    ...CATALOGUE_VIEW,
  ];
}

export function mockPermissionsFor(role: Role): MockModulePermission[] {
  switch (role) {
    case "employee":
      return fieldStaff("own");
    case "district_manager":
    case "state_manager":
      return manager("org_subtree");
    case "regional_manager":
      // Regional Managers watch subsidy applications but don't change them (handover).
      return [
        ...manager("territory").filter(
          (entry) => entry.module !== "subsidy" && entry.module !== "partners",
        ),
        grant("subsidy", ["view"], "territory"),
        // Regional Managers read partners only (RBAC.md §6.1).
        grant("partners", ["view"], "territory"),
      ];
    case "admin":
      return MODULE_CODES.map((module) => grant(module, PERMISSION_ACTIONS, "global"));
    case "account_manager":
      return [
        // Accounts records payments (RBAC.md §6.2: payments V:global CEA).
        grant("payments", ["view", "create", "edit", "approve"], "global"),
        // Accounts sees complaints (refunds are paid through them) but decides none.
        grant("complaints", ["view"], "global"),
        // Accounts decides the payment step of every order (RBAC.md §6.2).
        grant("sales_orders", ["view", "approve"], "global"),
        // Accounts follows subsidy applications without changing them (handover).
        grant("subsidy", ["view"], "global"),
        STOCK_VIEW,
        SCHEMES_VIEW,
        ...CATALOGUE_VIEW,
      ];
    case "dispatch_manager":
      return [
        // Dispatch approves the last step, then records what left (RBAC.md §6.2).
        grant("dispatch", ["view", "create", "edit", "approve"], "global"),
        grant("sales_orders", ["view", "approve"], "global"),
        // Dispatch records stock received and corrections (stock contract).
        grant("stock", ["view", "create"], "global"),
        SCHEMES_VIEW,
        ...CATALOGUE_VIEW,
      ];
    case "qa_manager":
      return [
        grant("complaints", ["view", "edit", "approve"], "global"),
        STOCK_VIEW,
        SCHEMES_VIEW,
        ...CATALOGUE_VIEW,
      ];
    case "distributor":
    case "dealer":
    case "sub_dealer":
      return channelPartner(role);
  }
}
