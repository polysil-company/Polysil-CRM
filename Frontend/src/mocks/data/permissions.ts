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

function fieldStaff(scope: Scope): MockModulePermission[] {
  return [
    grant("leads", ["view", "create", "edit"], scope),
    grant("quotations", ["view", "create", "edit"], scope),
    grant("sales_orders", ["view", "create", "edit"], scope),
    grant("subsidy", ["view", "create"], scope),
    grant("complaints", ["view", "create"], scope),
    grant("tasks", ["view", "create", "edit"], scope),
    grant("partners", ["view"], scope),
    SCHEMES_VIEW,
  ];
}

function manager(scope: Scope): MockModulePermission[] {
  return [
    // One entry per module, as GET /auth/me returns: the manager's replace the officer's.
    ...fieldStaff(scope).filter(
      (entry) => entry.module !== "quotations" && entry.module !== "sales_orders",
    ),
    // Managers approve orders and quotation discounts (RBAC.md §6.1).
    grant("quotations", ["view", "create", "edit", "approve"], scope),
    grant("sales_orders", ["view", "create", "edit", "approve"], scope),
    grant("reports", ["view"], scope),
  ];
}

function channelPartner(): MockModulePermission[] {
  return [
    grant("leads", ["view", "edit"], "partner_subtree"),
    grant("sales_orders", ["view", "create", "edit"], "partner_subtree"),
    grant("subsidy", ["view", "create"], "partner_subtree"),
    grant("complaints", ["view", "create"], "partner_subtree"),
    grant("marketing", ["view"], "global"),
    SCHEMES_VIEW,
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
      return manager("territory");
    case "admin":
      return MODULE_CODES.map((module) => grant(module, PERMISSION_ACTIONS, "global"));
    case "account_manager":
      return [
        grant("accounts", ["view", "edit", "approve"], "global"),
        // Accounts decides the payment step of every order (RBAC.md §6.2).
        grant("sales_orders", ["view", "approve"], "global"),
        SCHEMES_VIEW,
      ];
    case "dispatch_manager":
      return [
        // Dispatch approves the last step, then records what left (RBAC.md §6.2).
        grant("dispatch", ["view", "create", "edit", "approve"], "global"),
        grant("sales_orders", ["view", "approve"], "global"),
        SCHEMES_VIEW,
      ];
    case "qa_manager":
      return [grant("complaints", ["view", "edit", "approve"], "global"), SCHEMES_VIEW];
    case "distributor":
    case "dealer":
    case "sub_dealer":
      return channelPartner();
  }
}
