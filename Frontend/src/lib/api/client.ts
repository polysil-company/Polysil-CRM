import type { z } from "zod";

import type { DataId } from "@/lib/data-ids";
import { clientEnv } from "@/lib/env/client";
import { elapsedMs, isAbortError, type Logger } from "@/lib/logger";
import { REDACTED } from "@/lib/logger/redact";

import { ApiError, parseErrorBody, summarizeSchemaIssues, type HttpMethod } from "./errors";
import { createRequestId } from "./request-id";
import { buildApiUrl, type ApiPath, type QueryParams } from "./url";

export const DEFAULT_TIMEOUT_MS = 20_000;

/**
 * How a request authenticates:
 * - `required` (default): sends the access token, refreshing it first when it is
 *   about to expire, and retries once after a 401
 * - `optional`: sends the token only if one is at hand, and never refreshes (sign-out)
 * - `none`: the pre-auth endpoints — sign-in, one-time codes and refresh
 */
export type ApiAuth = "required" | "optional" | "none";

/** Supplies access tokens. lib/auth/session-store.ts registers the only implementation. */
export interface AccessTokenProvider {
  /** A usable token, refreshed first when needed or when `forceRefresh` is set; null once signed out. */
  getAccessToken(options: { readonly forceRefresh: boolean }): Promise<string | null>;
  /** The token in memory, without refreshing. */
  peekAccessToken(): string | null;
  /** The backend rejected a freshly refreshed token: the session is over. */
  onSessionRejected(): void;
}

let tokenProvider: AccessTokenProvider | null = null;

/**
 * Connects the client to the session. Without a provider (unit tests, Storybook)
 * requests are sent without an Authorization header.
 */
export function registerAccessTokenProvider(provider: AccessTokenProvider | null): void {
  tokenProvider = provider;
}

export interface ApiRequest<TSchema extends z.ZodType> {
  /** Functionality this call belongs to. Sent as `x-data-id` and written on every log line. */
  readonly dataId: DataId;
  /** Scoped logger of the calling module — `createLogger({ file })`. */
  readonly logger: Logger;
  /** Calling function name, for File → Function → Request → Response logs. */
  readonly fn: string;
  readonly method?: HttpMethod;
  readonly path: ApiPath;
  readonly query?: QueryParams;
  readonly body?: unknown;
  /** Schema of a successful response. Required — every response is validated. */
  readonly schema: TSchema;
  /** Pass TanStack Query's `signal` so abandoned requests are cancelled. */
  readonly signal?: AbortSignal | undefined;
  readonly timeoutMs?: number;
  /** Default `required`. See ApiAuth. */
  readonly auth?: ApiAuth;
  /** Keeps request and response bodies out of the logs: passwords, one-time codes, tokens. */
  readonly sensitive?: boolean;
  /**
   * `Idempotency-Key` for POST, PUT, PATCH and DELETE, which the backend requires
   * outside /auth. Generated per call when omitted. Pass the same key again to make a
   * user's retry of the same action safe to replay.
   */
  readonly idempotencyKey?: string;
}

const MUTATING_METHODS: ReadonlySet<HttpMethod> = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** The /auth mutations are replay-safe on the backend and take no Idempotency-Key. */
function needsIdempotencyKey(method: HttpMethod, path: ApiPath): boolean {
  return MUTATING_METHODS.has(method) && !path.startsWith("/auth/");
}

interface RequestContext {
  readonly dataId: DataId;
  readonly logger: Logger;
  readonly fn: string;
  readonly method: HttpMethod;
  readonly path: ApiPath;
  readonly url: string;
  readonly label: string;
  readonly requestId: string;
  readonly body: unknown;
  readonly sensitive: boolean;
  readonly idempotencyKey: string | undefined;
  readonly signal: AbortSignal | undefined;
  readonly timeoutMs: number;
  readonly startedAt: number;
}

interface RawResponse {
  readonly status: number;
  readonly ok: boolean;
  readonly payload: unknown;
}

/**
 * The ONLY way the app talks to the backend.
 *
 * Every call:
 *  - sends `x-request-id` (unique per call) and `x-data-id` (the functionality)
 *  - authenticates as `auth` says, refreshing and retrying once after a 401
 *  - sends an `Idempotency-Key` on mutations
 *  - logs the request (debug) and the response (info) or failure (warn/error)
 *  - validates the response body against `schema`; a mismatch throws an
 *    `ApiError` of kind "contract" (CONTRACT_VIOLATION) — a backend-side issue
 *  - throws only `ApiError`, except cancellations, which re-throw the
 *    original AbortError so TanStack Query treats them as cancelled
 */
export async function apiRequest<TSchema extends z.ZodType>(
  request: ApiRequest<TSchema>,
): Promise<z.output<TSchema>> {
  const method = request.method ?? "GET";
  const auth = request.auth ?? "required";
  const context: RequestContext = {
    dataId: request.dataId,
    logger: request.logger,
    fn: request.fn,
    method,
    path: request.path,
    url: buildApiUrl(request.path, request.query),
    label: `${method} ${request.path}`,
    requestId: createRequestId(),
    body: request.body,
    sensitive: request.sensitive ?? false,
    idempotencyKey: needsIdempotencyKey(method, request.path)
      ? (request.idempotencyKey ?? createRequestId())
      : undefined,
    signal: request.signal,
    timeoutMs: request.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    startedAt: performance.now(),
  };

  context.logger.debug(context.fn, `→ ${context.label}`, {
    ...traceOf(context),
    request: {
      method,
      url: context.url,
      query: request.query,
      body: context.sensitive && request.body !== undefined ? REDACTED : request.body,
    },
  });

  let response = await send(context, await tokenFor(auth, context));

  if (response.status === 401 && auth === "required" && tokenProvider !== null) {
    context.logger.debug(context.fn, `↻ ${context.label} 401, refreshing the session`, {
      ...traceOf(context),
    });
    const refreshed = await tokenProvider.getAccessToken({ forceRefresh: true });
    if (refreshed !== null) {
      response = await send(context, refreshed);
      if (response.status === 401) {
        tokenProvider.onSessionRejected();
      }
    }
  }

  return parseResponse(context, response, request.schema);
}

function traceOf(context: RequestContext): { dataId: DataId; requestId: string } {
  return { dataId: context.dataId, requestId: context.requestId };
}

async function tokenFor(auth: ApiAuth, context: RequestContext): Promise<string | null> {
  if (auth === "none" || tokenProvider === null) {
    return null;
  }
  if (auth === "optional") {
    return tokenProvider.peekAccessToken();
  }
  const token = await tokenProvider.getAccessToken({ forceRefresh: false });
  if (token === null) {
    const error = new ApiError({
      kind: "http",
      status: 401,
      code: "unauthenticated",
      message: `${context.label} needs a signed-in session`,
      dataId: context.dataId,
      requestId: context.requestId,
      method: context.method,
      path: context.path,
    });
    context.logger.debug(context.fn, `✕ ${context.label} not signed in`, {
      ...traceOf(context),
      error,
    });
    throw error;
  }
  return token;
}

async function send(context: RequestContext, token: string | null): Promise<RawResponse> {
  const timeout = createTimeoutSignal(context.signal, context.timeoutMs);

  try {
    const response = await fetch(context.url, {
      method: context.method,
      headers: buildHeaders(context, token),
      ...(context.body === undefined ? {} : { body: JSON.stringify(context.body) }),
      signal: timeout.signal,
      cache: "no-store",
      // The refresh cookie is same-origin and scoped to /api/v1/auth.
      credentials: "same-origin",
    });
    return { status: response.status, ok: response.ok, payload: await readBody(response) };
  } catch (error) {
    const durationMs = elapsedMs(context.startedAt);

    if (isAbortError(error) && !timeout.timedOut()) {
      context.logger.debug(context.fn, `✕ ${context.label} cancelled`, {
        ...traceOf(context),
        durationMs,
      });
      throw error;
    }

    const kind = timeout.timedOut() ? "timeout" : "network";
    const apiError = new ApiError({
      kind,
      message:
        kind === "timeout"
          ? `${context.label} timed out after ${context.timeoutMs}ms`
          : `${context.label} failed before a response was received`,
      dataId: context.dataId,
      requestId: context.requestId,
      method: context.method,
      path: context.path,
      cause: error,
    });
    context.logger.error(context.fn, `✕ ${context.label} ${kind}`, {
      ...traceOf(context),
      durationMs,
      error: apiError,
    });
    throw apiError;
  } finally {
    timeout.dispose();
  }
}

function parseResponse<TSchema extends z.ZodType>(
  context: RequestContext,
  response: RawResponse,
  schema: TSchema,
): z.output<TSchema> {
  const durationMs = elapsedMs(context.startedAt);
  const loggedPayload =
    context.sensitive && response.payload !== undefined ? REDACTED : response.payload;

  if (!response.ok) {
    const parsed = parseErrorBody(response.payload);
    const apiError = new ApiError({
      kind: "http",
      status: response.status,
      code: parsed.code,
      details: parsed.details,
      message: parsed.message ?? `${context.label} failed with status ${response.status}`,
      dataId: context.dataId,
      requestId: context.requestId,
      method: context.method,
      path: context.path,
    });
    const level = response.status >= 500 ? "error" : "warn";
    context.logger[level](context.fn, `✕ ${context.label} ${response.status}`, {
      ...traceOf(context),
      durationMs,
      error: apiError,
      // Error bodies carry codes and messages, never secrets, so they stay readable.
      response: response.payload,
    });
    throw apiError;
  }

  const result = schema.safeParse(response.payload);
  if (!result.success) {
    const apiError = new ApiError({
      kind: "contract",
      code: "CONTRACT_VIOLATION",
      status: response.status,
      message: `${context.label} returned data that does not match the ${context.dataId} contract`,
      details: summarizeSchemaIssues(result.error),
      dataId: context.dataId,
      requestId: context.requestId,
      method: context.method,
      path: context.path,
    });
    context.logger.error(context.fn, `✕ ${context.label} CONTRACT_VIOLATION`, {
      ...traceOf(context),
      durationMs,
      error: apiError,
      response: loggedPayload,
    });
    throw apiError;
  }

  context.logger.info(context.fn, `← ${context.label} ${response.status}`, {
    ...traceOf(context),
    durationMs,
    ...(context.logger.isLevelEnabled("debug")
      ? { response: context.sensitive ? REDACTED : result.data }
      : {}),
  });
  return result.data;
}

function buildHeaders(context: RequestContext, token: string | null): Headers {
  const headers = new Headers({
    accept: "application/json",
    "x-request-id": context.requestId,
    "x-data-id": context.dataId,
    "x-client": `polysil-web@${clientEnv.release}`,
  });
  if (context.body !== undefined) {
    headers.set("content-type", "application/json");
  }
  if (token !== null) {
    headers.set("authorization", `Bearer ${token}`);
  }
  if (context.idempotencyKey !== undefined) {
    headers.set("idempotency-key", context.idempotencyKey);
  }
  return headers;
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.length === 0) {
    return undefined;
  }
  try {
    const parsed: unknown = JSON.parse(text);
    return parsed;
  } catch {
    return text;
  }
}

interface TimeoutSignal {
  readonly signal: AbortSignal;
  timedOut(): boolean;
  dispose(): void;
}

/**
 * Combines the caller's signal with a timeout. Written by hand rather than
 * with `AbortSignal.any`, which older Safari versions on field devices lack.
 */
function createTimeoutSignal(external: AbortSignal | undefined, timeoutMs: number): TimeoutSignal {
  const controller = new AbortController();
  let didTimeout = false;

  const timer = setTimeout(() => {
    didTimeout = true;
    controller.abort(new DOMException("Request timed out", "TimeoutError"));
  }, timeoutMs);

  const forwardAbort = (): void => {
    controller.abort(external?.reason);
  };

  if (external?.aborted) {
    forwardAbort();
  } else {
    external?.addEventListener("abort", forwardAbort, { once: true });
  }

  return {
    signal: controller.signal,
    timedOut: () => didTimeout,
    dispose: () => {
      clearTimeout(timer);
      external?.removeEventListener("abort", forwardAbort);
    },
  };
}
