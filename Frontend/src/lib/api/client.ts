import type { z } from "zod";

import type { DataId } from "@/lib/data-ids";
import { clientEnv } from "@/lib/env/client";
import { elapsedMs, isAbortError, type Logger } from "@/lib/logger";

import { ApiError, parseErrorBody, summarizeSchemaIssues, type HttpMethod } from "./errors";
import { createRequestId } from "./request-id";
import { buildApiUrl, type ApiPath, type QueryParams } from "./url";

export const DEFAULT_TIMEOUT_MS = 20_000;

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
}

/**
 * The ONLY way the app talks to the backend.
 *
 * Every call:
 *  - sends `x-request-id` (unique per call) and `x-data-id` (the functionality)
 *  - logs the request (debug) and the response (info) or failure (warn/error)
 *  - validates the response body against `schema`; a mismatch throws an
 *    `ApiError` of kind "contract" (CONTRACT_VIOLATION) — a backend-side issue
 *  - throws only `ApiError`, except cancellations, which re-throw the
 *    original AbortError so TanStack Query treats them as cancelled
 */
export async function apiRequest<TSchema extends z.ZodType>(
  request: ApiRequest<TSchema>,
): Promise<z.output<TSchema>> {
  const { dataId, logger, fn, path, query, body, schema, signal } = request;
  const method = request.method ?? "GET";
  const timeoutMs = request.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const requestId = createRequestId();
  const url = buildApiUrl(path, query);
  const label = `${method} ${path}`;
  const trace = { dataId, requestId };
  const startedAt = performance.now();

  logger.debug(fn, `→ ${label}`, { ...trace, request: { method, url, query, body } });

  const timeout = createTimeoutSignal(signal, timeoutMs);
  let response: Response;
  let payload: unknown;

  try {
    response = await fetch(url, {
      method,
      headers: buildHeaders(dataId, requestId, body !== undefined),
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: timeout.signal,
      cache: "no-store",
      // TODO(AUTH-001): attach credentials or the auth header once the auth contract is agreed.
    });
    payload = await readBody(response);
  } catch (error) {
    const durationMs = elapsedMs(startedAt);

    if (isAbortError(error) && !timeout.timedOut()) {
      logger.debug(fn, `✕ ${label} cancelled`, { ...trace, durationMs });
      throw error;
    }

    const kind = timeout.timedOut() ? "timeout" : "network";
    const apiError = new ApiError({
      kind,
      message:
        kind === "timeout"
          ? `${label} timed out after ${timeoutMs}ms`
          : `${label} failed before a response was received`,
      dataId,
      requestId,
      method,
      path,
      cause: error,
    });
    logger.error(fn, `✕ ${label} ${kind}`, { ...trace, durationMs, error: apiError });
    throw apiError;
  } finally {
    timeout.dispose();
  }

  const durationMs = elapsedMs(startedAt);

  if (!response.ok) {
    const parsed = parseErrorBody(payload);
    const apiError = new ApiError({
      kind: "http",
      status: response.status,
      code: parsed.code,
      details: parsed.details,
      message: parsed.message ?? `${label} failed with status ${response.status}`,
      dataId,
      requestId,
      method,
      path,
    });
    const level = response.status >= 500 ? "error" : "warn";
    logger[level](fn, `✕ ${label} ${response.status}`, {
      ...trace,
      durationMs,
      error: apiError,
      response: payload,
    });
    throw apiError;
  }

  const result = schema.safeParse(payload);
  if (!result.success) {
    const apiError = new ApiError({
      kind: "contract",
      code: "CONTRACT_VIOLATION",
      status: response.status,
      message: `${label} returned data that does not match the ${dataId} contract`,
      details: summarizeSchemaIssues(result.error),
      dataId,
      requestId,
      method,
      path,
    });
    logger.error(fn, `✕ ${label} CONTRACT_VIOLATION`, {
      ...trace,
      durationMs,
      error: apiError,
      response: payload,
    });
    throw apiError;
  }

  logger.info(fn, `← ${label} ${response.status}`, {
    ...trace,
    durationMs,
    ...(logger.isLevelEnabled("debug") ? { response: result.data } : {}),
  });
  return result.data;
}

function buildHeaders(dataId: DataId, requestId: string, hasBody: boolean): Headers {
  const headers = new Headers({
    accept: "application/json",
    "x-request-id": requestId,
    "x-data-id": dataId,
    "x-client": `polysil-web@${clientEnv.release}`,
  });
  if (hasBody) {
    headers.set("content-type", "application/json");
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
