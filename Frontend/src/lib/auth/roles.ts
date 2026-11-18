/**
 * Role codes the backend assigns (`role.code` in `GET /auth/me`).
 *
 * Screens render the backend's `role.name` and gate on permissions, never on
 * these codes. The codes exist so the mock backend can preview each kind of user
 * and tests can read in business terms.
 *
 * TODO(AUTH-002): the backend seeds sixteen roles from its RBAC matrix; add the rest once that list is shared.
 */

/** Polysil staff, who sign in with a work email and password. */
export const STAFF_ROLES = [
  "employee",
  "district_manager",
  "state_manager",
  "regional_manager",
  "admin",
  "account_manager",
  "dispatch_manager",
  "qa_manager",
] as const;

/** Channel partner users, who sign in with a one-time code sent to their mobile. */
export const PARTNER_ROLES = ["distributor", "dealer", "sub_dealer"] as const;

export const ROLES = [...STAFF_ROLES, ...PARTNER_ROLES] as const;

export type StaffRole = (typeof STAFF_ROLES)[number];
export type PartnerRole = (typeof PARTNER_ROLES)[number];
export type Role = (typeof ROLES)[number];

export const ROLE_LABELS: Readonly<Record<Role, string>> = {
  employee: "Employee",
  district_manager: "District Manager",
  state_manager: "State Manager",
  regional_manager: "Regional Manager",
  admin: "Admin",
  account_manager: "Account Manager",
  dispatch_manager: "Dispatch Manager",
  qa_manager: "QA Manager",
  distributor: "Distributor",
  dealer: "Dealer",
  sub_dealer: "Sub-dealer",
};

/** Shown when a user holds no role (consumers). */
export const USER_TYPE_LABELS: Readonly<Record<"staff" | "partner_user" | "consumer", string>> = {
  staff: "Polysil staff",
  partner_user: "Channel partner",
  consumer: "Customer",
};

export function isPartnerRole(role: Role): role is PartnerRole {
  return PARTNER_ROLES.some((candidate) => candidate === role);
}
