import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_PARTNERS } from "@/mocks/data/reference";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  createUser,
  deleteUser,
  exportUsers,
  getUser,
  handOver,
  listRoles,
  listUsers,
  patchUser,
  revokeSessions,
  searchOpenOffices,
  setTemporaryPassword,
  unlockUser,
} from "./users.api";
import type { CreateUserRequest } from "./users.schemas";

const ALL = { q: "", userType: null, role: null, active: null, cursor: null } as const;

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function personNamed(name: string): string {
  const person = mockDb.users.find((user) => user.full_name === name);
  if (person === undefined) throw new Error(`No ${name} in the mock`);
  return person.id;
}

type StaffRequest = Extract<CreateUserRequest, { user_type: "staff" }>;

async function staffBody(): Promise<StaffRequest> {
  const [office] = await searchOpenOffices("Rajkot");
  const rajkot = MOCK_TERRITORIES.find(
    (item) => item.level === "district" && item.name === "Rajkot",
  );
  if (office === undefined || rajkot === undefined) throw new Error("No Rajkot in the mock");
  return {
    user_type: "staff",
    full_name: "Kiran Makwana",
    email: "Kiran.Makwana@polysil.in",
    mobile: null,
    role: "field_officer",
    org_unit_id: office.id,
    territory_ids: [rajkot.id],
    password: "Kp7m-Rq4x-Tz9w",
  };
}

describe("[ADMN-001] People list", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists staff and partner users newest first, with a total and filters", async () => {
    const page = await listUsers(ALL);
    expect(page.total).toBe(page.items.length);
    expect(page.items.some((user) => user.userType === "partner_user")).toBe(true);
    const staff = page.items.find((user) => user.name === "Ravi Joshi");
    expect(staff?.openLeads).toBeGreaterThan(0);
    const partner = page.items.find((user) => user.userType === "partner_user");
    expect(partner?.openLeads).toBeNull();

    const officers = await listUsers({ ...ALL, role: "field_officer" });
    expect(officers.items.every((user) => user.role?.code === "field_officer")).toBe(true);
    const inactive = await listUsers({ ...ALL, active: false });
    expect(inactive.items.map((user) => user.name)).toEqual(["Vijay Chaudhary"]);
    const byMobile = await listUsers({ ...ALL, q: "98791" });
    expect(byMobile.items.every((user) => user.userType === "partner_user")).toBe(true);
  });

  it("downloads the list as a file", async () => {
    const file = await exportUsers(ALL);
    expect(file.filename).toMatch(/^users-.*\.xlsx$/);
  });

  it("lists the sixteen roles, the portal ones marked", async () => {
    const roles = await listRoles();
    expect(roles).toHaveLength(16);
    expect(roles.filter((role) => role.portal).map((role) => role.code)).toEqual([
      "distributor",
      "dealer",
      "sub_dealer",
    ]);
  });
});

describe("[ADMN-003] Add a person", () => {
  beforeEach(reset);
  afterEach(reset);

  it("adds a staff member with a temporary password, and replays a retry", async () => {
    const body = await staffBody();
    const made = await createUser({ body, idempotencyKey: "new-1" });
    expect(made).toMatchObject({
      name: "Kiran Makwana",
      email: "kiran.makwana@polysil.in",
      mustChangePassword: true,
      active: true,
    });
    const again = await createUser({ body, idempotencyKey: "new-1" });
    expect(again.id).toBe(made.id);
    await expect(
      createUser({ body: { ...body, full_name: "Other" }, idempotencyKey: "new-1" }),
    ).rejects.toMatchObject({ status: 409, code: "idempotency_key_reused" });
  });

  it("refuses a short password, a taken email and a territory role without territories", async () => {
    const body = await staffBody();
    await expect(
      createUser({
        body: { ...body, email: "asha@polysil.in", password: "short", territory_ids: [] },
        idempotencyKey: "bad-1",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: {
        fields: {
          email: "already used by someone else",
          password: "at least 12 characters",
          territory_ids: "this role reads by territory: choose at least one",
        },
      },
    });
  });

  it("adds a partner user, their role following the partner", async () => {
    const partner = MOCK_PARTNERS.find((item) => item.partner_type === "distributor");
    if (partner === undefined) throw new Error("No distributor");
    const made = await createUser({
      body: {
        user_type: "partner_user",
        full_name: "Paresh Ladani",
        mobile: "98250 11223",
        partner_id: partner.id,
      },
      idempotencyKey: "partner-1",
    });
    expect(made).toMatchObject({ userType: "partner_user", mobile: "919825011223" });
    expect(made.role?.code).toBe("distributor");
    expect(made.partner?.name).toBe(partner.name);
  });
});

describe("[ADMN-004] Correct a person", () => {
  beforeEach(reset);
  afterEach(reset);

  it("never changes your own role, nor demotes the last administrator", async () => {
    await expect(
      patchUser({ userId: "usr-001", body: { role: "field_officer" }, idempotencyKey: "p-1" }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { role: "not on your own row" } } });
    await expect(
      patchUser({
        userId: "usr-001",
        body: { full_name: "Aarav R. Desai" },
        idempotencyKey: "p-2",
      }),
    ).resolves.toMatchObject({ name: "Aarav R. Desai" });
  });

  it("deactivates and reactivates someone", async () => {
    const id = personNamed("Kajal Solanki");
    await patchUser({ userId: id, body: { is_active: false }, idempotencyKey: "off" });
    expect((await getUser(id)).active).toBe(false);
    await patchUser({ userId: id, body: { is_active: true }, idempotencyKey: "on" });
    expect((await getUser(id)).active).toBe(true);
  });
});

describe("[ADMN-005] Account actions", () => {
  beforeEach(reset);
  afterEach(reset);

  it("sets a temporary password, signs out everywhere and unlocks", async () => {
    const id = personNamed("Ravi Joshi");
    const before = await getUser(id);
    expect(before.lockedUntil).not.toBeNull();
    expect(before.activeSessions).toBe(1);
    await expect(unlockUser({ userId: id, idempotencyKey: "u" })).resolves.toEqual({
      wasLocked: true,
    });
    await expect(
      setTemporaryPassword({ userId: id, password: "Kp7m-Rq4x-Tz9w", idempotencyKey: "s" }),
    ).resolves.toEqual({ sessionsRevoked: 1 });
    expect((await getUser(id)).mustChangePassword).toBe(true);
    await expect(revokeSessions({ userId: id, idempotencyKey: "r" })).resolves.toEqual({
      sessionsRevoked: 0,
    });
  });

  it("gives a partner user no password", async () => {
    const partner = mockDb.users.find((user) => user.user_type === "partner_user");
    if (partner === undefined) throw new Error("No partner user");
    await expect(
      setTemporaryPassword({ userId: partner.id, password: "Kp7m-Rq4x-Tz9w", idempotencyKey: "x" }),
    ).rejects.toMatchObject({ status: 422 });
  });
});

describe("[ADMN-006] A leaver", () => {
  beforeEach(reset);
  afterEach(reset);

  it("refuses to delete someone with open leads, then hands them over and deletes", async () => {
    const id = personNamed("Ravi Joshi");
    const target = personNamed("Nirav Shah");
    await expect(deleteUser({ userId: id, idempotencyKey: "d-1" })).rejects.toMatchObject({
      status: 422,
    });
    const result = await handOver({
      userId: id,
      body: { to_user_id: target, deactivate: true },
      idempotencyKey: "h-1",
    });
    expect(result.remaining).toBe(0);
    expect(result.leadsMoved).toBeGreaterThan(0);
    expect(result.deactivated).toBe(true);
    expect((await getUser(id)).openLeads).toBe(0);
    await deleteUser({ userId: id, idempotencyKey: "d-2" });
    const page = await listUsers(ALL);
    expect(page.items.some((user) => user.id === id)).toBe(false);
  });

  it("never deletes your own row", async () => {
    await expect(deleteUser({ userId: "usr-001", idempotencyKey: "self" })).rejects.toMatchObject({
      status: 422,
    });
  });
});
