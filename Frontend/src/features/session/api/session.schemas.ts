import { z } from "zod";

import { CHANNEL_PARTNER_TYPES, INTERNAL_ROLES } from "@/lib/auth/roles";

// TODO(AUTH-002): replace with the backend's GET /me contract once agreed.

const sessionUserSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  phone: z.string().min(1),
  email: z.email().nullable(),
  avatarUrl: z.url().nullable(),
});

/** Region-based visibility: what a user can SEE (permissions decide what they can DO). */
const regionScopeSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("own") }),
  z.object({ kind: z.literal("district"), districts: z.array(z.string()).min(1) }),
  z.object({ kind: z.literal("state"), states: z.array(z.string()).min(1) }),
  z.object({ kind: z.literal("region"), regions: z.array(z.string()).min(1) }),
  z.object({ kind: z.literal("global") }),
]);

const internalSessionSchema = z.object({
  user: sessionUserSchema,
  role: z.enum(INTERNAL_ROLES),
  scope: regionScopeSchema,
});

const channelPartnerSessionSchema = z.object({
  user: sessionUserSchema,
  role: z.literal("channel_partner"),
  partner: z.object({
    id: z.string().min(1),
    name: z.string().min(1),
    type: z.enum(CHANNEL_PARTNER_TYPES),
  }),
  scope: z.object({ kind: z.literal("own") }),
});

export const sessionSchema = z.union([internalSessionSchema, channelPartnerSessionSchema]);

export type Session = z.infer<typeof sessionSchema>;
