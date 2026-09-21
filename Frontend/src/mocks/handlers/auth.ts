import { http, HttpResponse } from "msw";
import { z } from "zod";

import { createRequestId } from "@/lib/api/request-id";
import { buildApiUrl } from "@/lib/api/url";
import { isPartnerRole } from "@/lib/auth/roles";
import {
  DEFAULT_MOCK_PARTNER_ROLE,
  DEFAULT_MOCK_ROLE,
  MOCK_OTP_CODE,
  MOCK_STAFF_PASSWORD,
  readMockRole,
  writeMockRole,
} from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";

import { applyScenario } from "./scenario";

/**
 * The backend's /auth endpoints (backend/docs/api/auth.md), mocked closely enough
 * to exercise every state of the sign-in screens:
 *
 *  - POST /auth/login        any email + MOCK_STAFF_PASSWORD; 5 failures in 15 min → 423 for 15 min
 *  - POST /auth/otp/request  always 202 with the same body; 422 for a malformed number
 *  - POST /auth/otp/verify   MOCK_OTP_CODE; 5 wrong attempts burn the code
 *  - POST /auth/refresh      rotates while the "refresh cookie" exists, else 401
 *  - POST /auth/logout       always 204
 *  - GET  /auth/me           needs a live Bearer token
 *
 * The httpOnly refresh cookie cannot be imitated from a service worker, so its
 * stand-in lives in localStorage. Every auth endpoint ignores the "error" scenario,
 * so the scenario menu can never lock a developer out.
 */

const ACCESS_TOKEN_SECONDS = 900;
/** The contract's defaults: the resend offer comes no sooner than the code expires. */
const OTP_EXPIRES_SECONDS = 300;
const OTP_RESEND_AFTER_SECONDS = 300;
const OTP_MAX_ATTEMPTS = 5;
const LOGIN_MAX_FAILURES = 5;
const LOGIN_WINDOW_MS = 15 * 60_000;
const MOBILE_PATTERN = /^[1-9]\d{9,14}$/;

const REFRESH_KEY = "polysil:mock-auth-refresh";
const OTP_KEY = "polysil:mock-auth-otp";
const FAILURES_KEY = "polysil:mock-auth-failures";

const otpChallengeSchema = z.object({
  mobile: z.string(),
  expiresAt: z.number(),
  attemptsLeft: z.number(),
});
const failuresSchema = z.record(
  z.string(),
  z.object({ count: z.number(), firstAt: z.number(), lockedUntil: z.number() }),
);

function readStored<TSchema extends z.ZodType>(
  key: string,
  schema: TSchema,
): z.output<TSchema> | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
      return null;
    }
    const parsed = schema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

function writeStored(key: string, value: unknown): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, JSON.stringify(value));
    }
  } catch {
    // Storage unavailable: the mock session lasts until the page reloads.
  }
}

function errorResponse(
  status: number,
  code: string,
  message: string,
  fields?: Record<string, string>,
): Response {
  return HttpResponse.json(
    { error: { code, message, ...(fields === undefined ? {} : { fields }) } },
    { status },
  );
}

async function readBody<TSchema extends z.ZodType>(
  request: Request,
  schema: TSchema,
): Promise<z.output<TSchema> | null> {
  try {
    const parsed = schema.safeParse(await request.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

function toE164WithoutPlus(mobile: string): string {
  return mobile.replace(/^\+/, "").replace(/\s/g, "");
}

/** Issues an access token and rotates the stand-in refresh cookie. */
function issueTokens(): Response {
  writeStored(REFRESH_KEY, createRequestId());
  const expiresAt = Date.now() + ACCESS_TOKEN_SECONDS * 1000;
  return HttpResponse.json({
    data: {
      access_token: `mock.${expiresAt}.${createRequestId()}`,
      token_type: "Bearer",
      expires_in: ACCESS_TOKEN_SECONDS,
    },
  });
}

function hasLiveAccessToken(request: Request): boolean {
  const match = /^Bearer mock\.(\d+)\.[\w-]+$/.exec(request.headers.get("authorization") ?? "");
  const hasSession = readStored(REFRESH_KEY, z.string()) !== null;
  return match !== null && Number(match[1]) > Date.now() && hasSession;
}

const loginBodySchema = z.object({ email: z.string(), password: z.string() });
const otpRequestBodySchema = z.object({ mobile: z.string() });
const otpVerifyBodySchema = z.object({ mobile: z.string(), code: z.string() });

export const authHandlers = [
  http.post(buildApiUrl("/auth/login"), async ({ request }) => {
    await applyScenario({ allowFailure: false });
    const body = await readBody(request, loginBodySchema);
    if (body === null) {
      return errorResponse(422, "validation_error", "Request validation failed.", {
        email: "Field required",
      });
    }

    const email = body.email.trim().toLowerCase();
    const now = Date.now();
    const failures = readStored(FAILURES_KEY, failuresSchema) ?? {};
    const current = failures[email];
    const record =
      current === undefined || now - current.firstAt > LOGIN_WINDOW_MS
        ? { count: 0, firstAt: now, lockedUntil: 0 }
        : current;

    if (record.lockedUntil > now) {
      return errorResponse(423, "account_locked", "Too many failed attempts. Try again later.");
    }

    if (body.password !== MOCK_STAFF_PASSWORD) {
      const count = record.count + 1;
      failures[email] = {
        count,
        firstAt: record.firstAt,
        lockedUntil: count >= LOGIN_MAX_FAILURES ? now + LOGIN_WINDOW_MS : 0,
      };
      writeStored(FAILURES_KEY, failures);
      return errorResponse(401, "invalid_credentials", "Email or password is incorrect.");
    }

    delete failures[email];
    writeStored(FAILURES_KEY, failures);
    if (isPartnerRole(readMockRole())) {
      writeMockRole(DEFAULT_MOCK_ROLE);
    }
    return issueTokens();
  }),

  http.post(buildApiUrl("/auth/otp/request"), async ({ request }) => {
    await applyScenario({ allowFailure: false });
    const body = await readBody(request, otpRequestBodySchema);
    const mobile = body === null ? "" : toE164WithoutPlus(body.mobile);
    if (!MOBILE_PATTERN.test(mobile)) {
      return errorResponse(422, "validation_error", "Request validation failed.", {
        mobile: "mobile must be E.164 digits without a leading plus",
      });
    }

    writeStored(OTP_KEY, {
      mobile,
      expiresAt: Date.now() + OTP_EXPIRES_SECONDS * 1000,
      attemptsLeft: OTP_MAX_ATTEMPTS,
    });
    return HttpResponse.json(
      {
        data: {
          sent: true,
          expires_in: OTP_EXPIRES_SECONDS,
          resend_after: OTP_RESEND_AFTER_SECONDS,
        },
      },
      { status: 202 },
    );
  }),

  http.post(buildApiUrl("/auth/otp/verify"), async ({ request }) => {
    await applyScenario({ allowFailure: false });
    const body = await readBody(request, otpVerifyBodySchema);
    if (body === null) {
      return errorResponse(422, "validation_error", "Request validation failed.", {
        code: "Field required",
      });
    }

    const challenge = readStored(OTP_KEY, otpChallengeSchema);
    const invalid = (): Response =>
      errorResponse(401, "invalid_otp", "That code is not valid. Request a new one.");

    if (
      challenge === null ||
      challenge.mobile !== toE164WithoutPlus(body.mobile) ||
      challenge.expiresAt <= Date.now() ||
      challenge.attemptsLeft <= 0
    ) {
      return invalid();
    }
    if (body.code.trim() !== MOCK_OTP_CODE) {
      writeStored(OTP_KEY, { ...challenge, attemptsLeft: challenge.attemptsLeft - 1 });
      return invalid();
    }

    writeStored(OTP_KEY, null);
    if (!isPartnerRole(readMockRole())) {
      writeMockRole(DEFAULT_MOCK_PARTNER_ROLE);
    }
    return issueTokens();
  }),

  http.post(buildApiUrl("/auth/refresh"), async () => {
    await applyScenario({ allowFailure: false });
    if (readStored(REFRESH_KEY, z.string()) === null) {
      return errorResponse(401, "invalid_refresh", "Sign in again.");
    }
    return issueTokens();
  }),

  http.post(buildApiUrl("/auth/logout"), async () => {
    await applyScenario({ allowFailure: false });
    writeStored(REFRESH_KEY, null);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(buildApiUrl("/auth/me"), async ({ request }) => {
    // The shell needs the session to show the scenario switcher, so it never fails.
    await applyScenario({ allowFailure: false });
    if (!hasLiveAccessToken(request)) {
      return errorResponse(401, "unauthenticated", "Not signed in.");
    }
    return HttpResponse.json(mockMeFor(readMockRole()));
  }),
];
