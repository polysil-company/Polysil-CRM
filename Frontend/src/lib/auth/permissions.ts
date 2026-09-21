/**
 * What the signed-in user may see and do, from `GET /auth/me` (AUTH-002).
 *
 * IMPORTANT: this only decides what the UI SHOWS. The backend checks every
 * permission again and row-level security scopes every list, so hiding a button
 * is a courtesy, never a guarantee.
 */

export const PERMISSION_ACTIONS = ["view", "create", "edit", "approve", "delete"] as const;

export type PermissionAction = (typeof PERMISSION_ACTIONS)[number];

/**
 * Backend module codes the UI gates on. `leads`, `partners`, `users` and `masters`
 * exist in the backend today; the others are the expected codes for modules that
 * are not built yet.
 *
 * TODO(AUTH-002): confirm the codes of unbuilt modules against the backend's RBAC matrix.
 */
export const MODULE_CODES = [
  "leads",
  "quotations",
  "orders",
  "approvals",
  "subsidy",
  "complaints",
  "tasks",
  "partners",
  "marketing",
  "schemes",
  "accounts",
  "dispatch",
  "reports",
  "masters",
  "users",
] as const;

export type ModuleCode = (typeof MODULE_CODES)[number];

/** One module's grants for the signed-in user, as `GET /auth/me` returns them. */
export interface ModulePermission {
  readonly module: string;
  /** Some of view, create, edit, approve and delete. Unknown actions are kept, not rejected. */
  readonly actions: readonly string[];
  /** own, org_subtree, territory, partner_subtree or global: how far the `view` grant reaches. */
  readonly scope: string | null;
}

/** Whether the permission list grants `action` on `module`. */
export function can(
  permissions: readonly ModulePermission[],
  module: ModuleCode,
  action: PermissionAction = "view",
): boolean {
  return permissions.some(
    (permission) => permission.module === module && permission.actions.includes(action),
  );
}
