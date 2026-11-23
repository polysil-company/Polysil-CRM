import type { MeResponse } from "@/features/session/api/session.schemas";
import {
  isPartnerRole,
  ROLE_LABELS,
  type PartnerRole,
  type Role,
  type StaffRole,
} from "@/lib/auth/roles";

import { mockPermissionsFor } from "./permissions";

const STAFF_ORG_UNITS: Readonly<Record<StaffRole, { id: string; name: string }>> = {
  employee: { id: "ou-vadodara-rural", name: "Vadodara Rural" },
  district_manager: { id: "ou-vadodara", name: "Vadodara District" },
  state_manager: { id: "ou-gujarat", name: "Gujarat" },
  regional_manager: { id: "ou-west", name: "West Region" },
  admin: { id: "ou-head-office", name: "Head Office" },
  account_manager: { id: "ou-head-office", name: "Head Office" },
  dispatch_manager: { id: "ou-head-office", name: "Head Office" },
  qa_manager: { id: "ou-head-office", name: "Head Office" },
};

const PARTNER_USERS: Readonly<
  Record<PartnerRole, { userId: string; fullName: string; partner: { id: string; name: string } }>
> = {
  distributor: {
    userId: "usr-101",
    fullName: "Mehul Patel",
    partner: { id: "prt-101", name: "Gujarat Agro Distributors" },
  },
  dealer: {
    userId: "usr-201",
    fullName: "Bhavesh Shah",
    partner: { id: "prt-201", name: "Shah Agro Traders" },
  },
  sub_dealer: {
    userId: "usr-301",
    fullName: "Ramesh Parmar",
    partner: { id: "prt-301", name: "Kisan Seva Kendra" },
  },
};

/** A believable GET /auth/me response for each role (switch roles from the user menu). */
export function mockMeFor(role: Role): MeResponse {
  const roleRef = { code: role, name: ROLE_LABELS[role] };
  const permissions = mockPermissionsFor(role);

  if (isPartnerRole(role)) {
    const { userId, fullName, partner } = PARTNER_USERS[role];
    return {
      data: {
        id: userId,
        full_name: fullName,
        user_type: "partner_user",
        role: roleRef,
        org_unit: null,
        partner,
        permissions,
      },
    };
  }

  return {
    data: {
      id: "usr-001",
      full_name: "Aarav Desai",
      user_type: "staff",
      role: roleRef,
      org_unit: STAFF_ORG_UNITS[role],
      partner: null,
      permissions,
    },
  };
}
