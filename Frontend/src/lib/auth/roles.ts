/**
 * Roles, as agreed with the client (Docs/Frontend-Scope.md §2).
 *
 * Internal roles are Polysil staff. Channel partners are external businesses
 * with a completely different set of screens; they have one role with three
 * types. The umbrella name "channel partner" is a placeholder until the client
 * confirms it.
 */

export const INTERNAL_ROLES = [
  "employee",
  "district_manager",
  "state_manager",
  "regional_manager",
  "admin",
  "account_manager",
  "dispatch_manager",
  "qa_manager",
] as const;

// TODO(AUTH-002): confirm the umbrella role name for distributor / dealer / sub-dealer with the client.
export const CHANNEL_PARTNER_ROLE = "channel_partner";

export const ROLES = [...INTERNAL_ROLES, CHANNEL_PARTNER_ROLE] as const;

export type Role = (typeof ROLES)[number];

export const CHANNEL_PARTNER_TYPES = ["distributor", "dealer", "sub_dealer"] as const;

export type ChannelPartnerType = (typeof CHANNEL_PARTNER_TYPES)[number];

export const ROLE_LABELS: Readonly<Record<Role, string>> = {
  employee: "Employee",
  district_manager: "District Manager",
  state_manager: "State Manager",
  regional_manager: "Regional Manager",
  admin: "Admin",
  account_manager: "Account Manager",
  dispatch_manager: "Dispatch Manager",
  qa_manager: "QA Manager",
  channel_partner: "Channel Partner",
};

export const CHANNEL_PARTNER_TYPE_LABELS: Readonly<Record<ChannelPartnerType, string>> = {
  distributor: "Distributor",
  dealer: "Dealer",
  sub_dealer: "Sub-dealer",
};
