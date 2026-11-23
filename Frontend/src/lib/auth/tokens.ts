import { z } from "zod";

/**
 * The backend's answer to sign-in and refresh (AUTH-001, AUTH-003, AUTH-004).
 *
 * The refresh token never appears here: the backend sets it as an httpOnly
 * cookie scoped to /api/v1/auth, where no script can read it.
 */
export const tokenResponseSchema = z
  .object({
    data: z.object({
      access_token: z.string().min(1),
      token_type: z.literal("Bearer"),
      expires_in: z.number().int().positive(),
    }),
  })
  .transform(({ data }) => ({
    accessToken: data.access_token,
    expiresInSeconds: data.expires_in,
  }));

export type SessionTokens = z.output<typeof tokenResponseSchema>;
