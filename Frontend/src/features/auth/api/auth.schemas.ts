import { z } from "zod";

import { normalizeIndianMobile } from "@/lib/format";

/**
 * Sign-in forms and the /auth contract (backend/docs/api/auth.md).
 * Token responses are shared with the session store: see lib/auth/tokens.ts.
 */

export const OTP_LENGTH = 6;

/** AUTH-003 · staff email and password. The password is sent exactly as typed. */
export const staffSignInFormSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Enter your work email.")
    .pipe(z.email("Enter a valid email address.")),
  password: z.string().min(1, "Enter your password."),
});

export type StaffSignInFormInput = z.input<typeof staffSignInFormSchema>;
export type StaffSignInRequest = z.output<typeof staffSignInFormSchema>;

/** The backend's length rule for a password (`identity.password_problem`): nothing else. */
export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

/**
 * AUTH-007 · changing your own password. Both passwords are sent exactly as typed; the
 * new one is typed twice so a slip doesn't lock the person out.
 */
export const changePasswordFormSchema = z
  .object({
    currentPassword: z.string().min(1, "Enter your current password."),
    newPassword: z
      .string()
      .min(1, "Choose a new password.")
      .min(PASSWORD_MIN_LENGTH, `At least ${String(PASSWORD_MIN_LENGTH)} characters.`)
      .max(PASSWORD_MAX_LENGTH, `At most ${String(PASSWORD_MAX_LENGTH)} characters.`),
    confirmPassword: z.string().min(1, "Type the new password again."),
  })
  .refine((values) => values.confirmPassword === values.newPassword, {
    path: ["confirmPassword"],
    message: "The two new passwords don't match.",
  });

export type ChangePasswordFormInput = z.input<typeof changePasswordFormSchema>;
export type ChangePasswordFormValues = z.output<typeof changePasswordFormSchema>;

/** POST /auth/password */
export interface ChangePasswordRequest {
  readonly current_password: string;
  readonly new_password: string;
}

/** AUTH-001 · an Indian mobile, typed any common way, sent as E.164 without the plus. */
export const mobileNumberFormSchema = z.object({
  mobile: z
    .string()
    .trim()
    .min(1, "Enter your mobile number.")
    .transform((value, context) => {
      const normalized = normalizeIndianMobile(value);
      if (normalized === null) {
        context.addIssue({ code: "custom", message: "Enter a 10-digit Indian mobile number." });
        return z.NEVER;
      }
      return normalized.slice(1);
    }),
});

export type MobileNumberFormInput = z.input<typeof mobileNumberFormSchema>;
export type MobileNumberFormValues = z.output<typeof mobileNumberFormSchema>;

/**
 * POST /auth/otp/request → 202. Identical whether or not the number is registered,
 * so it is never evidence that a code was sent.
 */
export const otpChallengeResponseSchema = z
  .object({
    data: z.object({
      sent: z.literal(true),
      expires_in: z.number().int().positive(),
      resend_after: z.number().int().nonnegative(),
    }),
  })
  .transform(({ data }) => ({
    expiresInSeconds: data.expires_in,
    resendAfterSeconds: data.resend_after,
  }));

export type OtpChallengeResponse = z.output<typeof otpChallengeResponseSchema>;

export interface OtpVerifyRequest {
  /** E.164 without the plus, e.g. 919876543210. */
  readonly mobile: string;
  readonly code: string;
}
