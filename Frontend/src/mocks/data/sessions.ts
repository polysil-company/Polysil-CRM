import type { Session } from "@/features/session/api/session.schemas";
import type { Role } from "@/lib/auth/roles";

const STAFF_USER = {
  id: "usr-001",
  name: "Aarav Desai",
  phone: "+919876543210",
  email: "aarav.desai@example.com",
  avatarUrl: null,
} as const;

/** A believable signed-in user for each role (switch roles from the user menu). */
export function mockSessionFor(role: Role): Session {
  switch (role) {
    case "channel_partner":
      return {
        user: { ...STAFF_USER, id: "usr-201", name: "Shree Krishna Agro", email: null },
        role,
        partner: { id: "cp-201", name: "Shree Krishna Agro", type: "dealer" },
        scope: { kind: "own" },
      };
    case "employee":
      return { user: STAFF_USER, role, scope: { kind: "own" } };
    case "district_manager":
      return {
        user: STAFF_USER,
        role,
        scope: { kind: "district", districts: ["Vadodara", "Anand"] },
      };
    case "state_manager":
      return { user: STAFF_USER, role, scope: { kind: "state", states: ["Gujarat"] } };
    case "regional_manager":
      return { user: STAFF_USER, role, scope: { kind: "region", regions: ["West"] } };
    case "admin":
    case "account_manager":
    case "dispatch_manager":
    case "qa_manager":
      return { user: STAFF_USER, role, scope: { kind: "global" } };
  }
}
