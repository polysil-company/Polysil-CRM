import type { Role } from "./roles";

/**
 * Permissions the UI checks before showing a screen, a navigation item or an
 * action.
 *
 * IMPORTANT: this only decides what the UI SHOWS. The backend is the authority
 * and must reject anything a role is not allowed to do.
 *
 * TODO(AUTH-002): replace ROLE_PERMISSIONS with the permission list returned by
 * GET /me once the backend contract exists. The matrix below is derived from
 * Docs/Frontend-Scope.md v0.3 and is a placeholder.
 */
export const PERMISSIONS = [
  "dashboard:view",
  "leads:view",
  "leads:create",
  "leads:assign",
  "quotations:view",
  "sales_orders:view",
  "approvals:view",
  "complaints:view",
  "qa:review",
  "dispatch:manage",
  "accounts:manage",
  "tasks:view",
  "tasks:assign",
  "channel_partners:view",
  "marketing:view",
  "marketing:manage",
  "schemes:view",
  "schemes:manage",
  "masters:manage",
  "users:manage",
  "reports:view",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

const EMPLOYEE: readonly Permission[] = [
  "dashboard:view",
  "leads:view",
  "leads:create",
  "quotations:view",
  "sales_orders:view",
  "complaints:view",
  "tasks:view",
  "schemes:view",
];

const MANAGER: readonly Permission[] = [
  ...EMPLOYEE,
  "leads:assign",
  "approvals:view",
  "tasks:assign",
  "channel_partners:view",
  "reports:view",
];

export const ROLE_PERMISSIONS: Readonly<Record<Role, readonly Permission[]>> = {
  employee: EMPLOYEE,
  district_manager: MANAGER,
  state_manager: MANAGER,
  regional_manager: MANAGER,
  // Admin sets Marketing and Schemes but does not see the channel-partner offers feed.
  admin: PERMISSIONS.filter((permission) => permission !== "marketing:view"),
  // Account, Dispatch and QA are single-person work queues with global scope.
  account_manager: ["dashboard:view", "approvals:view", "accounts:manage", "schemes:view"],
  dispatch_manager: [
    "dashboard:view",
    "approvals:view",
    "dispatch:manage",
    "sales_orders:view",
    "schemes:view",
  ],
  qa_manager: ["dashboard:view", "approvals:view", "complaints:view", "qa:review", "schemes:view"],
  // Marketing is visible to channel partners only; Schemes are visible to everyone.
  channel_partner: [
    "dashboard:view",
    "leads:view",
    "leads:create",
    "sales_orders:view",
    "complaints:view",
    "marketing:view",
    "schemes:view",
  ],
};

export function can(role: Role, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role].includes(permission);
}
