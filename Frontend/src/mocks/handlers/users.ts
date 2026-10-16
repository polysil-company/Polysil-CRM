import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { UserPageWire, UserRowWire } from "@/features/users/api/users.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can, type PermissionAction } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { normalizeIndianMobile } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, MOCK_PARTNERS, MOCK_STAFF, mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { findMockTerritory } from "@/mocks/data/territories";
import {
  MOCK_ADMIN_ROLES,
  MOCK_ROLES,
  MOCK_TERRITORY_ROLES,
  type MockUserRecord,
} from "@/mocks/data/users";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse, mockWorkbook } from "./shared";

/**
 * ADMN-001…006 · People, with the backend's rules (`users.md`, handover
 * `administration-and-sign-in.md`):
 *  - a staff member needs an email, a non-portal role, an open office and a temporary password
 *    of 12 or more; a partner user a mobile and an active partner, the role following its type;
 *  - nobody changes their own role, office, partner, territories or active flag;
 *  - the last administrator is never deactivated, demoted or deleted;
 *  - delete is refused while the person owns open leads: hand over first, 500 at a time.
 */

const PASSWORD_MIN = 12;
const HANDOVER_BATCH = 500;
const OPEN_STAGES_EXCLUDED = new Set(["won", "lost", "merged"]);

function allowed(action: PermissionAction): boolean {
  return can(mockPermissionsFor(readMockRole()), "users", action);
}

function forbidden(): Response {
  return errorResponse(403, "insufficient_permission", "You may not do this.");
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function notFound(): Response {
  return errorResponse(404, "not_found", "No such person in your scope.");
}

function myId(): string {
  return mockMeFor(readMockRole()).data.id;
}

function live(): MockUserRecord[] {
  return mockDb.users.filter((user) => user.deleted_at === null);
}

function openLeadsOf(userId: string): number {
  return mockDb.leads.filter(
    (lead) => lead.owner?.id === userId && !OPEN_STAGES_EXCLUDED.has(lead.stage),
  ).length;
}

/** The row as the API sends it: open leads counted now, and nothing a row doesn't carry. */
function toRow(user: MockUserRecord): UserRowWire {
  return {
    id: user.id,
    user_type: user.user_type,
    full_name: user.full_name,
    email: user.email,
    mobile: user.mobile,
    role: user.role,
    org_unit: user.org_unit,
    partner: user.partner,
    is_active: user.is_active,
    must_change_password: user.must_change_password,
    last_login_at: user.last_login_at,
    open_leads: user.user_type === "staff" ? openLeadsOf(user.id) : null,
  };
}

function toDetail(user: MockUserRecord): Record<string, unknown> {
  const editor = allowed("edit");
  const lockedUntil =
    user.locked_until !== null && Date.parse(user.locked_until) > Date.now()
      ? user.locked_until
      : null;
  return {
    ...toRow(user),
    territories: user.territories,
    locked_until: editor && user.user_type === "staff" ? lockedUntil : null,
    active_sessions: editor ? user.active_sessions : null,
    password_changed_at: user.password_changed_at,
    created_at: user.created_at,
    deleted_at: user.deleted_at,
    created_by: user.created_by,
  };
}

function matches(user: MockUserRecord, url: URL): boolean {
  const params = url.searchParams;
  const q = (params.get("q") ?? "").trim().toLowerCase();
  if (q !== "") {
    const digits = q.replace(/\D/g, "");
    const hit =
      user.full_name.toLowerCase().includes(q) ||
      (user.email ?? "").includes(q) ||
      (digits.length >= 3 && /^\+?\d[\d\s]*$/.test(q) && (user.mobile ?? "").includes(digits));
    if (!hit) return false;
  }
  const type = params.get("user_type");
  if (type !== null ? user.user_type !== type : false) return false;
  const role = params.get("role");
  if (role !== null && user.role?.code !== role) return false;
  const active = params.get("is_active");
  if (active !== null && String(user.is_active) !== active) return false;
  return true;
}

function filtered(url: URL): MockUserRecord[] {
  return live()
    .filter((user) => matches(user, url))
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function find(userId: string): MockUserRecord | undefined {
  return live().find((user) => user.id === userId);
}

/** Whether `user` stops being an active administrator leaves nobody holding users.edit. */
function isLastAdmin(user: MockUserRecord): boolean {
  if (!user.is_active || user.role === null || !MOCK_ADMIN_ROLES.has(user.role.code)) return false;
  return !live().some(
    (other) =>
      other.id !== user.id &&
      other.is_active &&
      other.role !== null &&
      MOCK_ADMIN_ROLES.has(other.role.code),
  );
}

function roleOf(code: string): { code: string; name: string; portal: boolean } | null {
  const role = MOCK_ROLES.find((item) => item.code === code);
  return role === undefined ? null : { code: role.code, name: role.name, portal: role.is_portal };
}

function openOffice(officeId: string): { id: string; name: string } | null {
  const office = mockDb.offices.find((item) => item.id === officeId && item.is_open);
  return office === undefined ? null : { id: office.id, name: office.name };
}

function territoryRefs(
  ids: readonly string[],
): { id: string; name: string; level: string }[] | null {
  const refs = ids.map((territoryId) => findMockTerritory(territoryId));
  if (refs.some((ref) => ref === undefined)) return null;
  return refs.flatMap((ref) =>
    ref === undefined ? [] : [{ id: ref.id, name: ref.name, level: ref.level }],
  );
}

function mobileOf(value: string): string | null {
  const normalized = normalizeIndianMobile(value);
  return normalized === null ? null : normalized.slice(1);
}

function takenBy(field: "email" | "mobile", value: string, except: string | null): boolean {
  return live().some((user) => user.id !== except && user[field] === value);
}

const createSchema = z.discriminatedUnion("user_type", [
  z.object({
    user_type: z.literal("staff"),
    full_name: z.string().trim().min(1, "Field required").max(200),
    email: z.email("Not an email address").transform((value) => value.trim().toLowerCase()),
    mobile: z.string().nullish(),
    role: z.string().min(1, "Field required"),
    org_unit_id: z.string().min(1, "Field required"),
    territory_ids: z.array(z.string()).default([]),
    password: z.string(),
  }),
  z.object({
    user_type: z.literal("partner_user"),
    full_name: z.string().trim().min(1, "Field required").max(200),
    mobile: z.string().min(1, "Field required"),
    partner_id: z.string().min(1, "Field required"),
  }),
]);

const patchSchema = z.object({
  full_name: z.string().trim().min(1).max(200).optional(),
  email: z.string().optional(),
  mobile: z.string().optional(),
  role: z.string().optional(),
  org_unit_id: z.string().optional(),
  partner_id: z.string().optional(),
  territory_ids: z.array(z.string()).optional(),
  is_active: z.boolean().optional(),
});

function fieldsOf(error: z.ZodError): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const issue of error.issues)
    fields[issue.path.map(String).join(".") || "body"] = issue.message;
  return fields;
}

function newUserId(): string {
  return mockUuid(MOCK_ID_SPACE.staff, 1000 + mockDb.users.length);
}

const base = (rest = ""): string => buildApiUrl(`/users${rest}`);

export const userHandlers = [
  http.get(buildApiUrl("/lookups/roles"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    return HttpResponse.json({ data: MOCK_ROLES });
  }),

  http.get(buildApiUrl("/org-units"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const params = new URL(request.url).searchParams;
    const q = (params.get("q") ?? "").trim().toLowerCase();
    const open = params.get("is_open");
    const rows = mockDb.offices
      .filter((office) => (q === "" ? true : office.name.toLowerCase().includes(q)))
      .filter((office) => (open === null ? true : String(office.is_open) === open))
      .map((office) => ({
        ...office,
        active_users: live().filter((user) => user.is_active && user.org_unit?.id === office.id)
          .length,
      }));
    return HttpResponse.json({ data: rows, meta: { limit: 50 } });
  }),

  http.get(base(), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? "25");
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const rows = scenario === "empty" ? [] : filtered(url);
    const page = rows.slice(offset, offset + limit);
    const next = offset + limit < rows.length ? encodeCursor(offset + limit) : null;
    const body: UserPageWire = {
      data: page.map(toRow),
      meta: {
        limit,
        ...(next === null ? {} : { next_cursor: next }),
        ...(url.searchParams.get("include_total") === "true" ? { total: rows.length } : {}),
      },
    };
    return HttpResponse.json(body);
  }),

  /** Before /users/:userId. */
  http.get(base("/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const rows = filtered(new URL(request.url));
    if (rows.length > 5000) {
      return errorResponse(422, "export_too_large", "More than 5,000 rows: narrow the filters.");
    }
    return mockWorkbook(
      "users",
      ["Name", "Type", "Role", "Office or partner", "Email", "Mobile", "Active"],
      rows.map((user) => [
        user.full_name,
        user.user_type,
        user.role?.name ?? "",
        user.org_unit?.name ?? user.partner?.name ?? "",
        user.email ?? "",
        user.mobile ?? "",
        user.is_active ? "yes" : "no",
      ]),
    );
  }),

  http.get(base("/:userId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const user = mockDb.users.find((item) => item.id === params.userId);
    if (user === undefined || (user.deleted_at !== null && !allowed("delete"))) return notFound();
    return HttpResponse.json({ data: toDetail(user) });
  }),

  http.post(base(), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("create")) return forbidden();
    const key = request.headers.get("idempotency-key");
    if (key === null)
      return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
    const raw = await request.text();
    const replay = mockDb.userWrites.get(key);
    if (replay !== undefined) {
      if (replay.body !== raw) {
        return errorResponse(
          409,
          "idempotency_key_reused",
          "The key was used for a different body.",
        );
      }
      const made = mockDb.users.find((user) => user.id === replay.userId);
      if (made !== undefined) return HttpResponse.json({ data: toDetail(made) }, { status: 201 });
    }
    const parsed = createSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const now = new Date().toISOString();
    const me = mockDb.users.find((user) => user.id === myId());
    const createdBy = me === undefined ? null : { id: me.id, full_name: me.full_name };
    let person: MockUserRecord;
    if (body.user_type === "staff") {
      const fields: Record<string, string> = {};
      if (takenBy("email", body.email, null)) fields.email = "already used by someone else";
      const mobile =
        body.mobile == null || body.mobile.trim() === "" ? null : mobileOf(body.mobile);
      if (body.mobile != null && body.mobile.trim() !== "" && mobile === null) {
        fields.mobile = "not an Indian mobile number";
      } else if (mobile !== null && takenBy("mobile", mobile, null)) {
        fields.mobile = "already used by someone else";
      }
      const role = roleOf(body.role);
      if (role === null) fields.role = "no such role";
      else if (role.portal) fields.role = "a partner user's role; choose a staff role";
      const office = openOffice(body.org_unit_id);
      if (office === null) fields.org_unit_id = "not an open office";
      const territories = territoryRefs(body.territory_ids);
      if (territories === null) fields.territory_ids = "a territory that doesn't exist";
      else if (role !== null && MOCK_TERRITORY_ROLES.has(role.code) && territories.length === 0) {
        fields.territory_ids = "this role reads by territory: choose at least one";
      }
      if (body.password.length < PASSWORD_MIN) {
        fields.password = `at least ${String(PASSWORD_MIN)} characters`;
      }
      if (
        Object.keys(fields).length > 0 ||
        role === null ||
        office === null ||
        territories === null
      ) {
        return invalid(fields);
      }
      person = {
        id: newUserId(),
        user_type: "staff",
        full_name: body.full_name,
        email: body.email,
        mobile,
        role: { code: role.code, name: role.name },
        org_unit: office,
        partner: null,
        is_active: true,
        must_change_password: true,
        last_login_at: null,
        open_leads: 0,
        territories,
        locked_until: null,
        active_sessions: 0,
        password_changed_at: null,
        created_at: now,
        deleted_at: null,
        created_by: createdBy,
      };
    } else {
      const fields: Record<string, string> = {};
      const mobile = mobileOf(body.mobile);
      if (mobile === null) fields.mobile = "not an Indian mobile number";
      else if (takenBy("mobile", mobile, null)) fields.mobile = "already used by someone else";
      const partner = MOCK_PARTNERS.find((item) => item.id === body.partner_id);
      if (partner === undefined) fields.partner_id = "not an active partner";
      if (Object.keys(fields).length > 0 || partner === undefined || mobile === null) {
        return invalid(fields);
      }
      const role = roleOf(partner.partner_type);
      person = {
        id: newUserId(),
        user_type: "partner_user",
        full_name: body.full_name,
        email: null,
        mobile,
        role: role === null ? null : { code: role.code, name: role.name },
        org_unit: null,
        partner: { id: partner.id, name: partner.name },
        is_active: true,
        must_change_password: false,
        last_login_at: null,
        open_leads: null,
        territories: [],
        locked_until: null,
        active_sessions: 0,
        password_changed_at: null,
        created_at: now,
        deleted_at: null,
        created_by: createdBy,
      };
    }
    mockDb.users.push(person);
    mockDb.userWrites.set(key, { body: raw, userId: person.id });
    return HttpResponse.json({ data: toDetail(person) }, { status: 201 });
  }),

  http.patch(base("/:userId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const user = find(String(params.userId));
    if (user === undefined) return notFound();
    const parsed = patchSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const fields: Record<string, string> = {};
    const own = user.id === myId();
    const staff = user.user_type === "staff";
    for (const field of [
      "role",
      "org_unit_id",
      "partner_id",
      "territory_ids",
      "is_active",
    ] as const) {
      if (own && body[field] !== undefined) fields[field] = "not on your own row";
    }
    if (!staff) {
      for (const field of ["email", "role", "org_unit_id", "territory_ids"] as const) {
        if (body[field] !== undefined) fields[field] = "staff only";
      }
    } else if (body.partner_id !== undefined) {
      fields.partner_id = "partner users only";
    }
    let email = user.email;
    if (body.email !== undefined && staff) {
      const parsedEmail = z.email().safeParse(body.email.trim().toLowerCase());
      if (!parsedEmail.success) fields.email = "not an email address";
      else if (takenBy("email", parsedEmail.data, user.id))
        fields.email = "already used by someone else";
      else email = parsedEmail.data;
    }
    let mobile = user.mobile;
    if (body.mobile !== undefined) {
      const next = mobileOf(body.mobile);
      if (next === null) fields.mobile = "not an Indian mobile number";
      else if (takenBy("mobile", next, user.id)) fields.mobile = "already used by someone else";
      else mobile = next;
    }
    const role = body.role === undefined ? null : roleOf(body.role);
    if (body.role !== undefined && (role === null || role.portal)) fields.role = "not a staff role";
    const office = body.org_unit_id === undefined ? null : openOffice(body.org_unit_id);
    if (body.org_unit_id !== undefined && office === null)
      fields.org_unit_id = "not an open office";
    const partner =
      body.partner_id === undefined
        ? null
        : (MOCK_PARTNERS.find((item) => item.id === body.partner_id) ?? null);
    if (body.partner_id !== undefined && partner === null)
      fields.partner_id = "not an active partner";
    const territories = body.territory_ids === undefined ? null : territoryRefs(body.territory_ids);
    if (body.territory_ids !== undefined && territories === null) {
      fields.territory_ids = "a territory that doesn't exist";
    }
    const nextRole = role ?? user.role;
    const nextTerritories = territories ?? user.territories;
    if (
      staff &&
      nextRole !== null &&
      MOCK_TERRITORY_ROLES.has(nextRole.code) &&
      nextTerritories.length === 0 &&
      fields.territory_ids === undefined
    ) {
      fields.territory_ids = "this role reads by territory: choose at least one";
    }
    const demoted = role !== null && !MOCK_ADMIN_ROLES.has(role.code);
    if ((body.is_active === false || demoted) && isLastAdmin(user)) {
      fields.id = `${user.full_name} is the last administrator`;
    }
    if (
      body.is_active === true &&
      staff &&
      user.org_unit !== null &&
      openOffice(user.org_unit.id) === null &&
      office === null
    ) {
      fields.is_active = "their office is closed: choose an open one";
    }
    if (Object.keys(fields).length > 0) return invalid(fields);

    user.full_name = body.full_name ?? user.full_name;
    user.email = email;
    user.mobile = mobile;
    if (role !== null) user.role = { code: role.code, name: role.name };
    if (office !== null) user.org_unit = office;
    if (partner !== null) {
      user.partner = { id: partner.id, name: partner.name };
      const partnerRole = roleOf(partner.partner_type);
      user.role =
        partnerRole === null ? user.role : { code: partnerRole.code, name: partnerRole.name };
    }
    if (territories !== null) user.territories = territories;
    if (body.is_active !== undefined) {
      user.is_active = body.is_active;
      if (!body.is_active) user.active_sessions = 0;
    }
    return HttpResponse.json({ data: toDetail(user) });
  }),

  http.post(base("/:userId/password"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const user = find(String(params.userId));
    if (user === undefined) return notFound();
    if (user.user_type !== "staff") {
      return invalid({ user_type: "a partner user signs in by code and has no password" });
    }
    const parsed = z.object({ password: z.string() }).safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    if (parsed.data.password.length < PASSWORD_MIN) {
      return invalid({ password: `at least ${String(PASSWORD_MIN)} characters` });
    }
    const revoked = user.active_sessions;
    user.active_sessions = 0;
    user.must_change_password = true;
    user.locked_until = null;
    user.password_changed_at = new Date().toISOString();
    return HttpResponse.json({
      data: { id: user.id, must_change_password: true, sessions_revoked: revoked },
    });
  }),

  http.post(base("/:userId/sessions/revoke"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const user = find(String(params.userId));
    if (user === undefined) return notFound();
    const revoked = user.active_sessions;
    user.active_sessions = 0;
    return HttpResponse.json({ data: { id: user.id, sessions_revoked: revoked } });
  }),

  http.post(base("/:userId/unlock"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const user = find(String(params.userId));
    if (user === undefined) return notFound();
    if (user.user_type !== "staff") {
      return invalid({ user_type: "a partner user signs in by code; there is nothing to unlock" });
    }
    const wasLocked = user.locked_until !== null && Date.parse(user.locked_until) > Date.now();
    user.locked_until = null;
    return HttpResponse.json({ data: { id: user.id, was_locked: wasLocked } });
  }),

  http.post(base("/:userId/handover"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const leaver = find(String(params.userId));
    if (leaver === undefined) return notFound();
    const parsed = z
      .object({ to_user_id: z.string().min(1), deactivate: z.boolean().default(false) })
      .safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const { to_user_id: toUserId, deactivate } = parsed.data;
    const target =
      live().find((user) => user.id === toUserId && user.is_active && user.user_type === "staff") ??
      MOCK_STAFF.find((person) => person.id === toUserId);
    if (target === undefined || toUserId === leaver.id) {
      return invalid({ to_user_id: "an active staff member who can work leads, not the leaver" });
    }
    if (deactivate && leaver.id === myId()) {
      return invalid({ deactivate: "never your own row" });
    }
    const owner = { id: target.id, full_name: target.full_name };
    const open = mockDb.leads.filter(
      (lead) => lead.owner?.id === leaver.id && !OPEN_STAGES_EXCLUDED.has(lead.stage),
    );
    const moving = open.slice(0, HANDOVER_BATCH);
    for (const lead of moving) lead.owner = owner;
    const remaining = open.length - moving.length;
    let tasksMoved = 0;
    for (const task of mockDb.tasks) {
      if (task.status === "open" && task.assigned_to?.id === leaver.id) {
        task.assigned_to = owner;
        tasksMoved += 1;
      }
    }
    if (deactivate && remaining > 0) {
      return invalid({ deactivate: "hand over every open lead first" });
    }
    if (deactivate) {
      if (isLastAdmin(leaver))
        return invalid({ id: `${leaver.full_name} is the last administrator` });
      leaver.is_active = false;
      leaver.active_sessions = 0;
    }
    return HttpResponse.json({
      data: {
        leads_moved: moving.length,
        remaining,
        tasks_moved: tasksMoved,
        deactivated: deactivate,
      },
    });
  }),

  http.delete(base("/:userId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("delete")) return forbidden();
    const user = mockDb.users.find((item) => item.id === params.userId);
    if (user === undefined) return notFound();
    if (user.deleted_at !== null) return new HttpResponse(null, { status: 204 });
    if (user.id === myId()) return invalid({ id: "not your own row" });
    const leads = user.user_type === "staff" ? openLeadsOf(user.id) : 0;
    if (leads > 0) {
      return invalid({ open_leads: `owns ${String(leads)} open leads: hand them over first` });
    }
    if (isLastAdmin(user)) return invalid({ id: `${user.full_name} is the last administrator` });
    user.deleted_at = new Date().toISOString();
    user.is_active = false;
    user.active_sessions = 0;
    return new HttpResponse(null, { status: 204 });
  }),
];
