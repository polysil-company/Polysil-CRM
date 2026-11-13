import type { OfficeWire, RoleItemWire, UserDetailWire } from "@/features/users/api/users.schemas";

import {
  MOCK_DISTRICT_OFFICES,
  MOCK_ID_SPACE,
  MOCK_PARTNERS,
  MOCK_STATE_OFFICE,
  mockUuid,
} from "./reference";
import { MOCK_TASK_ME, MOCK_TEAM } from "./tasks";
import { MOCK_TERRITORIES } from "./territories";

/**
 * ADMN-001…006 · The mock's people: the signed-in user (usr-001), the staff who own the mock's
 * leads and tasks, the head-office desks, and one user per channel partner. Invented people.
 */

/** A person as the mock keeps them: the detail the API returns, plus what it hides. */
export interface MockUserRecord extends UserDetailWire {
  /** Live sessions; returned only to a `users.edit` holder. */
  active_sessions: number;
  locked_until: string | null;
}

/**
 * The sixteen roles of `identity.ASSIGNABLE_ROLES`, never `system`. The names and the
 * levels are the mock's own; the backend's seed owns the real ones.
 */
export const MOCK_ROLES: readonly RoleItemWire[] = [
  {
    code: "field_officer",
    name: "Field Officer",
    level: 1,
    is_functional: false,
    is_portal: false,
  },
  {
    code: "district_manager",
    name: "District Manager",
    level: 2,
    is_functional: false,
    is_portal: false,
  },
  {
    code: "state_manager",
    name: "State Manager",
    level: 3,
    is_functional: false,
    is_portal: false,
  },
  {
    code: "regional_manager",
    name: "Regional Manager",
    level: 4,
    is_functional: false,
    is_portal: false,
  },
  { code: "admin_sales", name: "Admin-Sales", level: 5, is_functional: false, is_portal: false },
  { code: "md_ceo", name: "MD / CEO", level: 5, is_functional: false, is_portal: false },
  {
    code: "account_manager",
    name: "Account Manager",
    level: 5,
    is_functional: true,
    is_portal: false,
  },
  {
    code: "dispatch_manager",
    name: "Dispatch Manager",
    level: 5,
    is_functional: true,
    is_portal: false,
  },
  { code: "qc_manager", name: "QC Manager", level: 5, is_functional: true, is_portal: false },
  {
    code: "state_coordinator",
    name: "State Coordinator",
    level: 3,
    is_functional: true,
    is_portal: false,
  },
  { code: "marketing", name: "Marketing", level: 5, is_functional: true, is_portal: false },
  { code: "support", name: "Support", level: 5, is_functional: true, is_portal: false },
  { code: "board", name: "Board", level: 5, is_functional: false, is_portal: false },
  { code: "distributor", name: "Distributor", level: 3, is_functional: false, is_portal: true },
  { code: "dealer", name: "Dealer", level: 2, is_functional: false, is_portal: true },
  { code: "sub_dealer", name: "Sub-dealer", level: 1, is_functional: false, is_portal: true },
];

/** Roles that read by territory: without a territory they see nothing (the mock's list). */
export const MOCK_TERRITORY_ROLES: ReadonlySet<string> = new Set([
  "field_officer",
  "district_manager",
  "state_manager",
  "regional_manager",
  "state_coordinator",
]);

/** Roles that hold `users.edit` in the mock: the "last administrator" rule counts these. */
export const MOCK_ADMIN_ROLES: ReadonlySet<string> = new Set(["admin_sales", "md_ceo"]);

const CREATED = "2026-06-01T05:30:00Z";

function roleRef(code: string): { code: string; name: string } {
  const role = MOCK_ROLES.find((item) => item.code === code);
  return { code, name: role?.name ?? code };
}

/** The offices: the state office and the district ones, as `mockOfficeFor` numbers them. */
export function seedOffices(): OfficeWire[] {
  const named = [MOCK_STATE_OFFICE, ...Object.values(MOCK_DISTRICT_OFFICES)];
  const state = MOCK_TERRITORIES.find((territory) => territory.level === "state") ?? null;
  const offices: OfficeWire[] = named.map((name, index) => {
    const district = Object.entries(MOCK_DISTRICT_OFFICES).find(([, office]) => office === name);
    const territory =
      district === undefined
        ? state
        : (MOCK_TERRITORIES.find(
            (item) => item.level === "district" && item.name === district[0],
          ) ?? null);
    return {
      id: mockUuid(MOCK_ID_SPACE.orgUnit, index + 1),
      name,
      role_level: district === undefined ? 3 : 2,
      parent:
        index === 0 ? null : { id: mockUuid(MOCK_ID_SPACE.orgUnit, 1), name: MOCK_STATE_OFFICE },
      territory:
        territory === null
          ? null
          : { id: territory.id, name: territory.name, level: territory.level },
      is_open: true,
      closed_at: null,
      active_users: 0,
      created_at: CREATED,
    };
  });
  offices.push(
    {
      id: mockUuid(MOCK_ID_SPACE.orgUnit, 50),
      name: "Head Office",
      role_level: 5,
      parent: null,
      territory: null,
      is_open: true,
      closed_at: null,
      active_users: 0,
      created_at: CREATED,
    },
    {
      id: mockUuid(MOCK_ID_SPACE.orgUnit, 51),
      name: "Bhavnagar District (closed)",
      role_level: 2,
      parent: { id: mockUuid(MOCK_ID_SPACE.orgUnit, 1), name: MOCK_STATE_OFFICE },
      territory: null,
      is_open: false,
      closed_at: "2026-08-01T05:30:00Z",
      active_users: 0,
      created_at: CREATED,
    },
  );
  return offices;
}

function districtRef(name: string): { id: string; name: string; level: string } {
  const territory = MOCK_TERRITORIES.find(
    (item) => item.level === "district" && item.name === name,
  );
  return {
    id: territory?.id ?? `district-${name}`,
    name,
    level: "district",
  };
}

interface StaffSeed {
  readonly id: string;
  readonly name: string;
  readonly email: string;
  readonly role: string;
  readonly office: string;
  readonly districts: readonly string[];
  readonly active?: boolean;
  readonly mustChange?: boolean;
  readonly lastLogin?: string | null;
  readonly lockedUntil?: string | null;
  readonly sessions?: number;
}

function emailOf(name: string): string {
  return `${name.toLowerCase().replace(/[^a-z]+/g, ".")}@polysil.in`;
}

export function seedUsers(): MockUserRecord[] {
  const offices = seedOffices();
  const officeRef = (name: string): { id: string; name: string } | null => {
    const office = offices.find((item) => item.name === name);
    return office === undefined ? null : { id: office.id, name: office.name };
  };
  const [ravi, bharat, kajal, nirav, asha] = [
    MOCK_TEAM.find((person) => person.full_name === "Ravi Joshi"),
    MOCK_TEAM.find((person) => person.full_name === "Bharat Vaghela"),
    MOCK_TEAM.find((person) => person.full_name === "Kajal Solanki"),
    MOCK_TEAM.find((person) => person.full_name === "Nirav Shah"),
    MOCK_TEAM.find((person) => person.full_name === "Asha Patel"),
  ];
  const staff: StaffSeed[] = [
    {
      id: MOCK_TASK_ME.id,
      name: MOCK_TASK_ME.full_name,
      email: "aarav.desai@polysil.in",
      role: "admin_sales",
      office: "Head Office",
      districts: [],
      lastLogin: "2026-10-10T03:40:00Z",
      sessions: 2,
    },
    {
      id: asha?.id ?? mockUuid(MOCK_ID_SPACE.staff, 2),
      name: "Asha Patel",
      email: "asha@polysil.in",
      role: "state_manager",
      office: MOCK_STATE_OFFICE,
      districts: ["Rajkot", "Junagadh", "Amreli"],
      lastLogin: "2026-10-09T12:10:00Z",
      sessions: 1,
    },
    {
      id: ravi?.id ?? mockUuid(MOCK_ID_SPACE.staff, 3),
      name: "Ravi Joshi",
      email: emailOf("Ravi Joshi"),
      role: "field_officer",
      office: "Rajkot District",
      districts: ["Rajkot"],
      lastLogin: "2026-10-09T09:05:00Z",
      sessions: 1,
      // Five wrong passwords a few minutes ago: locked for the rest of the fifteen.
      lockedUntil: new Date(Date.now() + 12 * 60_000).toISOString(),
    },
    {
      id: bharat?.id ?? mockUuid(MOCK_ID_SPACE.staff, 4),
      name: "Bharat Vaghela",
      email: emailOf("Bharat Vaghela"),
      role: "field_officer",
      office: "Junagadh District",
      districts: ["Junagadh"],
      lastLogin: "2026-10-08T11:00:00Z",
    },
    {
      id: kajal?.id ?? mockUuid(MOCK_ID_SPACE.staff, 5),
      name: "Kajal Solanki",
      email: emailOf("Kajal Solanki"),
      role: "field_officer",
      office: "Amreli District",
      districts: ["Amreli"],
      lastLogin: "2026-10-07T06:30:00Z",
    },
    {
      id: nirav?.id ?? mockUuid(MOCK_ID_SPACE.staff, 6),
      name: "Nirav Shah",
      email: emailOf("Nirav Shah"),
      role: "district_manager",
      office: "Rajkot District",
      districts: ["Rajkot"],
      lastLogin: "2026-10-09T15:45:00Z",
    },
    {
      id: mockUuid(MOCK_ID_SPACE.staff, 20),
      name: "Meena Rathod",
      email: emailOf("Meena Rathod"),
      role: "account_manager",
      office: "Head Office",
      districts: [],
      lastLogin: "2026-10-09T05:20:00Z",
    },
    {
      id: mockUuid(MOCK_ID_SPACE.staff, 21),
      name: "Dilip Parmar",
      email: emailOf("Dilip Parmar"),
      role: "dispatch_manager",
      office: "Head Office",
      districts: [],
      lastLogin: "2026-10-08T04:50:00Z",
    },
    {
      id: mockUuid(MOCK_ID_SPACE.staff, 22),
      name: "Hansa Gohil",
      email: emailOf("Hansa Gohil"),
      role: "qc_manager",
      office: "Head Office",
      districts: [],
      lastLogin: null,
      mustChange: true,
    },
    {
      id: mockUuid(MOCK_ID_SPACE.staff, 23),
      name: "Vijay Chaudhary",
      email: emailOf("Vijay Chaudhary"),
      role: "field_officer",
      office: "Amreli District",
      districts: ["Amreli"],
      active: false,
      lastLogin: "2026-07-14T10:00:00Z",
    },
  ];

  const createdBy = { id: MOCK_TASK_ME.id, full_name: MOCK_TASK_ME.full_name };
  const people: MockUserRecord[] = staff.map((person, index) => ({
    id: person.id,
    user_type: "staff",
    full_name: person.name,
    email: person.email,
    mobile: `9198250${String(40000 + index * 137).padStart(5, "0")}`,
    role: roleRef(person.role),
    org_unit: officeRef(person.office),
    partner: null,
    is_active: person.active ?? true,
    must_change_password: person.mustChange ?? false,
    last_login_at: person.lastLogin ?? null,
    open_leads: 0,
    territories: person.districts.map(districtRef),
    locked_until: person.lockedUntil ?? null,
    active_sessions: person.sessions ?? 0,
    password_changed_at: person.mustChange === true ? null : "2026-06-02T05:30:00Z",
    created_at: `2026-06-${String(1 + index).padStart(2, "0")}T05:30:00Z`,
    deleted_at: null,
    created_by: index === 0 ? null : createdBy,
  }));

  for (const [index, partner] of MOCK_PARTNERS.slice(0, 6).entries()) {
    people.push({
      id: mockUuid(MOCK_ID_SPACE.staff, 100 + index),
      user_type: "partner_user",
      full_name: partner.contact_person,
      email: null,
      mobile: `9198791${String(10000 + index * 211).padStart(5, "0")}`,
      role: roleRef(partner.partner_type),
      org_unit: null,
      partner: { id: partner.id, name: partner.name },
      is_active: true,
      must_change_password: false,
      last_login_at: index % 2 === 0 ? "2026-10-05T07:00:00Z" : null,
      open_leads: null,
      territories: [],
      locked_until: null,
      active_sessions: 0,
      password_changed_at: null,
      created_at: `2026-07-${String(1 + index).padStart(2, "0")}T05:30:00Z`,
      deleted_at: null,
      created_by: createdBy,
    });
  }
  return people;
}
