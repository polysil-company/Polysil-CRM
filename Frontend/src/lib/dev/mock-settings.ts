import { ROLES, type PartnerRole, type Role, type StaffRole } from "@/lib/auth/roles";

/**
 * Developer controls for the mock backend (MSW). Only meaningful when
 * NEXT_PUBLIC_API_MOCKING is `enabled` — or `partial`, for the modules still mocked there;
 * the mock role does nothing in `partial`, where the real session decides. Stored per
 * browser in localStorage.
 *
 * Scenarios let anyone preview every UI state in the real app without
 * editing code: slow network, empty results, server error, contract violation.
 */

export const MOCK_SCENARIOS = ["realistic", "slow", "empty", "error", "contract"] as const;

export type MockScenario = (typeof MOCK_SCENARIOS)[number];

export const MOCK_SCENARIO_LABELS: Readonly<Record<MockScenario, string>> = {
  realistic: "Realistic data",
  slow: "Slow network (3 s)",
  empty: "Empty results",
  error: "Server error (500)",
  contract: "Contract violation",
};

/** Who a staff sign-in becomes in the mock backend, unless a staff role is already chosen. */
export const DEFAULT_MOCK_ROLE: StaffRole = "state_manager";

/** Who a one-time-code sign-in becomes, unless a partner role is already chosen. */
export const DEFAULT_MOCK_PARTNER_ROLE: PartnerRole = "dealer";

/**
 * Demo credentials the mock backend accepts (AUTH-001, AUTH-003). Not secrets: they
 * only work against MSW, which the build refuses to enable in staging and production.
 */
export const MOCK_STAFF_PASSWORD = "polysil-demo";
export const MOCK_OTP_CODE = "123456";

const SCENARIO_KEY = "polysil:mock-scenario";
const ROLE_KEY = "polysil:mock-role";
const MUST_CHANGE_PASSWORD_KEY = "polysil:mock-must-change-password";
const STAFF_PASSWORD_KEY = "polysil:mock-staff-password";

function readStorage(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable — the default applies.
  }
}

export function readMockScenario(): MockScenario {
  const stored = readStorage(SCENARIO_KEY);
  return MOCK_SCENARIOS.find((scenario) => scenario === stored) ?? "realistic";
}

export function writeMockScenario(scenario: MockScenario): void {
  writeStorage(SCENARIO_KEY, scenario);
}

export function readMockRole(): Role {
  const stored = readStorage(ROLE_KEY);
  return ROLES.find((role) => role === stored) ?? DEFAULT_MOCK_ROLE;
}

export function writeMockRole(role: Role): void {
  writeStorage(ROLE_KEY, role);
}

/**
 * AUTH-007 · Whether the mock backend treats the signed-in staff member as holding a
 * temporary password: `/auth/me` says so and every other call answers 403
 * `password_change_required` until it is changed.
 */
export function readMockMustChangePassword(): boolean {
  return readStorage(MUST_CHANGE_PASSWORD_KEY) === "1";
}

export function writeMockMustChangePassword(value: boolean): void {
  writeStorage(MUST_CHANGE_PASSWORD_KEY, value ? "1" : "0");
}

/**
 * The password a staff member changed to in the mock, or null. Sign-in accepts it as well as
 * MOCK_STAFF_PASSWORD, so a demo can never lock itself out.
 */
export function readMockChangedPassword(): string | null {
  return readStorage(STAFF_PASSWORD_KEY);
}

export function writeMockChangedPassword(password: string): void {
  writeStorage(STAFF_PASSWORD_KEY, password);
}
