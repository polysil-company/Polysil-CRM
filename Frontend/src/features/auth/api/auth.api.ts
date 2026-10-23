import { z } from "zod";

import { apiRequest } from "@/lib/api/client";
import { tokenResponseSchema, type SessionTokens } from "@/lib/auth/tokens";
import { createLogger } from "@/lib/logger";

import {
  otpChallengeResponseSchema,
  type ChangePasswordRequest,
  type OtpChallengeResponse,
  type OtpVerifyRequest,
  type StaffSignInRequest,
} from "./auth.schemas";

const log = createLogger({ file: "features/auth/api/auth.api.ts", dataId: "AUTH-001" });

/** AUTH-003 · POST /auth/login. 401 invalid_credentials, 423 account_locked, 422. */
export function signInWithPassword(credentials: StaffSignInRequest): Promise<SessionTokens> {
  return apiRequest({
    dataId: "AUTH-003",
    logger: log,
    fn: "signInWithPassword",
    method: "POST",
    path: "/auth/login",
    body: credentials,
    schema: tokenResponseSchema,
    auth: "none",
    sensitive: true,
  });
}

/** AUTH-001 · POST /auth/otp/request. Always 202; 422 for a malformed number. */
export function requestOtp(mobile: string): Promise<OtpChallengeResponse> {
  return apiRequest({
    dataId: "AUTH-001",
    logger: log,
    fn: "requestOtp",
    method: "POST",
    path: "/auth/otp/request",
    // The logger masks the number to its last four digits.
    body: { mobile },
    schema: otpChallengeResponseSchema,
    auth: "none",
  });
}

/** AUTH-001 · POST /auth/otp/verify. 401 invalid_otp covers wrong, expired and burned codes. */
export function verifyOtp(request: OtpVerifyRequest): Promise<SessionTokens> {
  return apiRequest({
    dataId: "AUTH-001",
    logger: log,
    fn: "verifyOtp",
    method: "POST",
    path: "/auth/otp/verify",
    body: request,
    schema: tokenResponseSchema,
    auth: "none",
    sensitive: true,
  });
}

/**
 * AUTH-005 · POST /auth/logout. Always 204. Sends the access token when there is one;
 * the refresh cookie identifies the session when it has already expired.
 */
export function signOut(): Promise<undefined> {
  return apiRequest({
    dataId: "AUTH-005",
    logger: log,
    fn: "signOut",
    method: "POST",
    path: "/auth/logout",
    schema: z.undefined(),
    auth: "optional",
  });
}

/**
 * AUTH-007 · POST /auth/password: change your own password (staff only). 204, after which
 * every session, this one included, is signed out. 422 `fields.current_password` when the
 * current one is wrong, `fields.new_password` when the new one is refused; 409
 * `password_changed_meanwhile` when an administrator reset it in between. The one call,
 * besides `GET /auth/me`, that works while a temporary password is in force.
 */
export function changeOwnPassword({
  body,
  idempotencyKey,
}: {
  body: ChangePasswordRequest;
  idempotencyKey: string;
}): Promise<undefined> {
  return apiRequest({
    dataId: "AUTH-007",
    logger: log,
    fn: "changeOwnPassword",
    method: "POST",
    path: "/auth/password",
    body,
    idempotencyKey,
    schema: z.undefined(),
    sensitive: true,
  });
}
