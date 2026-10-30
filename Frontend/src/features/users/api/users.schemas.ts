import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * ADMN-001…006 · People: staff and partner users (`backend/docs/api/users.md`, handover
 * `administration-and-sign-in.md`). Every key of a row is always present; null means "not
 * set", never "hidden". `open_leads` is filled for staff and null for partner users;
 * `locked_until` and `active_sessions` only for a caller who holds `users.edit`.
 */

const id = z.string().min(1);
const isoDateTime = z.string().min(1);

export const USER_TYPES = ["staff", "partner_user"] as const;
export type UserType = (typeof USER_TYPES)[number];
const userTypeSchema = z.enum(USER_TYPES);

const roleRefSchema = z.object({ code: z.string().min(1), name: z.string() });
const orgUnitRefSchema = z.object({ id, name: z.string() });
/** The name is null when the partner row is outside the caller's partner scope. */
const partnerRefSchema = z.object({ id, name: z.string().nullish() });
const territoryRefSchema = z.object({ id, name: z.string(), level: z.string() });
const userRefSchema = z.object({ id, full_name: z.string() });

const userRowWireSchema = z.object({
  id,
  user_type: userTypeSchema,
  full_name: z.string(),
  email: z.string().nullable(),
  mobile: z.string().nullable(),
  role: roleRefSchema.nullable(),
  org_unit: orgUnitRefSchema.nullable(),
  partner: partnerRefSchema.nullable(),
  is_active: z.boolean(),
  must_change_password: z.boolean(),
  last_login_at: isoDateTime.nullable(),
  open_leads: z.number().int().nonnegative().nullable(),
});

export type UserRowWire = z.input<typeof userRowWireSchema>;

/** A person, as screens read them. */
export interface UserRow {
  readonly id: string;
  readonly userType: UserType;
  readonly name: string;
  readonly email: string | null;
  readonly mobile: string | null;
  readonly role: { readonly code: string; readonly name: string } | null;
  readonly office: { readonly id: string; readonly name: string } | null;
  readonly partner: { readonly id: string; readonly name: string | null } | null;
  readonly active: boolean;
  readonly mustChangePassword: boolean;
  readonly lastLoginAt: string | null;
  /** Staff only; null for a partner user, who owns no leads. */
  readonly openLeads: number | null;
}

function toRow(wire: z.output<typeof userRowWireSchema>): UserRow {
  return {
    id: wire.id,
    userType: wire.user_type,
    name: wire.full_name,
    email: wire.email,
    mobile: wire.mobile,
    role: wire.role,
    office: wire.org_unit,
    partner:
      wire.partner === null ? null : { id: wire.partner.id, name: wire.partner.name ?? null },
    active: wire.is_active,
    mustChangePassword: wire.must_change_password,
    lastLoginAt: wire.last_login_at,
    openLeads: wire.open_leads,
  };
}

const userRowSchema = userRowWireSchema.transform(toRow);

export const userPageSchema = cursorPageSchema(userRowSchema);
export type UserPage = CursorPage<UserRow>;
export interface UserPageWire {
  readonly data: UserRowWire[];
  readonly meta: PageMetaWire;
}

const userDetailWireSchema = userRowWireSchema.extend({
  territories: z.array(territoryRefSchema),
  /** Staff only, and only for a `users.edit` holder: the end of a live sign-in lockout. */
  locked_until: isoDateTime.nullish(),
  /** Live sessions, for a `users.edit` holder; null otherwise. */
  active_sessions: z.number().int().nonnegative().nullish(),
  password_changed_at: isoDateTime.nullable(),
  created_at: isoDateTime,
  deleted_at: isoDateTime.nullable(),
  created_by: userRefSchema.nullable(),
});

export type UserDetailWire = z.input<typeof userDetailWireSchema>;

export const userDetailSchema = z.object({ data: userDetailWireSchema }).transform(({ data }) => ({
  ...toRow(data),
  territories: data.territories,
  lockedUntil: data.locked_until ?? null,
  activeSessions: data.active_sessions ?? null,
  passwordChangedAt: data.password_changed_at,
  createdAt: data.created_at,
  deletedAt: data.deleted_at,
  createdBy:
    data.created_by === null ? null : { id: data.created_by.id, name: data.created_by.full_name },
}));

export type UserDetail = z.output<typeof userDetailSchema>;

/** GET /users and /users/export filters, as the URL keeps them. */
export interface UserListParams {
  readonly q: string;
  readonly userType: UserType | null;
  readonly role: string | null;
  /** null for everyone, active or not. */
  readonly active: boolean | null;
  readonly cursor: string | null;
}

/** POST /users */
export type CreateUserRequest =
  | {
      readonly user_type: "staff";
      readonly full_name: string;
      readonly email: string;
      readonly mobile: string | null;
      readonly role: string;
      readonly org_unit_id: string;
      readonly territory_ids: readonly string[];
      /** A temporary password of at least 12 characters, told to the person out of band. */
      readonly password: string;
    }
  | {
      readonly user_type: "partner_user";
      readonly full_name: string;
      readonly mobile: string;
      readonly partner_id: string;
    };

/** PATCH /users/{id}: only what changes. `territory_ids` replaces the whole set. */
export interface PatchUserRequest {
  readonly full_name?: string;
  readonly email?: string;
  readonly mobile?: string;
  readonly role?: string;
  readonly org_unit_id?: string;
  readonly partner_id?: string;
  readonly territory_ids?: readonly string[];
  readonly is_active?: boolean;
}

export const passwordSetResultSchema = z
  .object({
    data: z.object({
      id,
      must_change_password: z.boolean().default(true),
      sessions_revoked: z.number().int().nonnegative(),
    }),
  })
  .transform(({ data }) => ({ sessionsRevoked: data.sessions_revoked }));

export const revokeResultSchema = z
  .object({ data: z.object({ id, sessions_revoked: z.number().int().nonnegative() }) })
  .transform(({ data }) => ({ sessionsRevoked: data.sessions_revoked }));

export const unlockResultSchema = z
  .object({ data: z.object({ id, was_locked: z.boolean() }) })
  .transform(({ data }) => ({ wasLocked: data.was_locked }));

export const handoverResultSchema = z
  .object({
    data: z.object({
      leads_moved: z.number().int().nonnegative(),
      remaining: z.number().int().nonnegative(),
      tasks_moved: z.number().int().nonnegative().default(0),
      deactivated: z.boolean(),
    }),
  })
  .transform(({ data }) => ({
    leadsMoved: data.leads_moved,
    remaining: data.remaining,
    tasksMoved: data.tasks_moved,
    deactivated: data.deactivated,
  }));

export type HandoverResult = z.output<typeof handoverResultSchema>;

/** POST /users/{id}/handover */
export interface HandoverRequest {
  readonly to_user_id: string;
  readonly deactivate: boolean;
}

// ── the pickers the form needs ──────────────────────────────────────────────────

const roleItemSchema = z.object({
  code: z.string().min(1),
  name: z.string(),
  level: z.number().int(),
  is_functional: z.boolean(),
  /** A partner user's role: never offered on the staff form. */
  is_portal: z.boolean(),
});

export type RoleItemWire = z.input<typeof roleItemSchema>;

/** GET /lookups/roles */
export const roleListSchema = z.object({ data: z.array(roleItemSchema) }).transform(({ data }) =>
  data.map((role) => ({
    code: role.code,
    name: role.name,
    level: role.level,
    portal: role.is_portal,
  })),
);

export type RoleItem = z.output<typeof roleListSchema>[number];

const officeSchema = z.object({
  id,
  name: z.string(),
  role_level: z.number().int(),
  parent: z.object({ id, name: z.string() }).nullable(),
  territory: territoryRefSchema.nullable(),
  is_open: z.boolean(),
  closed_at: isoDateTime.nullable(),
  active_users: z.number().int().nonnegative(),
  created_at: isoDateTime,
});

export type OfficeWire = z.input<typeof officeSchema>;

/** GET /org-units: the office picker reads the open ones, by name. */
export const officePageSchema = cursorPageSchema(
  officeSchema.transform((office) => ({
    id: office.id,
    name: office.name,
    parentName: office.parent?.name ?? null,
    territoryName: office.territory?.name ?? null,
  })),
);

export type OfficeChoice = z.output<typeof officePageSchema>["items"][number];
