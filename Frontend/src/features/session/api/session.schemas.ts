import { z } from "zod";

/**
 * AUTH-002 · GET /auth/me — who the signed-in user is and what to render for them.
 * Contract: backend/api/schemas/auth.py (MeResponse), backend/docs/api/auth.md.
 *
 * Optional fields are read leniently (missing or null) and normalised to null, so
 * an additive backend change never breaks the shell. Unknown modules and actions
 * are kept: the UI simply has no screen for them yet.
 */

const refSchema = z.object({ id: z.string().min(1), name: z.string().min(1) });

const modulePermissionSchema = z.object({
  module: z.string().min(1),
  actions: z.array(z.string()),
  scope: z.string().nullish(),
});

export const meResponseSchema = z
  .object({
    data: z.object({
      id: z.string().min(1),
      full_name: z.string().min(1),
      user_type: z.enum(["staff", "partner_user", "consumer"]),
      role: z.object({ code: z.string().min(1), name: z.string().min(1) }).nullish(),
      /** Staff only. Never set together with `partner`. */
      org_unit: refSchema.nullish(),
      /** Portal users only. The name stays null until the channel module lands. */
      partner: z.object({ id: z.string().min(1), name: z.string().nullish() }).nullish(),
      permissions: z.array(modulePermissionSchema).optional(),
      /**
       * AUTH-007 · A temporary password set by an administrator is in force: until it is
       * changed, every call but this one and `POST /auth/password` answers 403
       * `password_change_required`.
       */
      must_change_password: z.boolean().nullish(),
    }),
  })
  .transform(({ data }) => ({
    user: { id: data.id, name: data.full_name },
    userType: data.user_type,
    role: data.role ?? null,
    orgUnit: data.org_unit ?? null,
    partner: data.partner ? { id: data.partner.id, name: data.partner.name ?? null } : null,
    permissions: (data.permissions ?? []).map((permission) => ({
      module: permission.module,
      actions: permission.actions,
      scope: permission.scope ?? null,
    })),
    mustChangePassword: data.must_change_password === true,
  }));

/** The backend's JSON, as the mock backend must produce it. */
export type MeResponse = z.input<typeof meResponseSchema>;

/** The signed-in user, as screens read it. */
export type Session = z.output<typeof meResponseSchema>;
