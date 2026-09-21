import { z } from "zod";

import type { DataId } from "@/lib/data-ids";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * - network:  the request never got a response (offline, DNS, CORS, server down)
 * - timeout:  no response within the time limit
 * - http:     the backend answered with a non-2xx status
 * - contract: the backend answered 2xx but the body broke the agreed schema
 * - unknown:  anything else (a frontend bug)
 */
export type ApiErrorKind = "network" | "timeout" | "http" | "contract" | "unknown";

/** Where to start investigating. */
export type ErrorSource = "frontend" | "backend" | "network" | "unknown";

export interface ApiErrorInit {
  readonly kind: ApiErrorKind;
  readonly message: string;
  readonly dataId: DataId;
  readonly requestId: string;
  readonly method: HttpMethod;
  readonly path: string;
  readonly status?: number | undefined;
  readonly code?: string | undefined;
  readonly details?: unknown;
  readonly cause?: unknown;
}

/** The only error type thrown by `apiRequest`. */
export class ApiError extends Error {
  override readonly name = "ApiError";
  readonly kind: ApiErrorKind;
  readonly dataId: DataId;
  readonly requestId: string;
  readonly method: HttpMethod;
  readonly path: string;
  readonly status: number | undefined;
  readonly code: string | undefined;
  readonly details: unknown;

  constructor(init: ApiErrorInit) {
    super(init.message, init.cause === undefined ? undefined : { cause: init.cause });
    this.kind = init.kind;
    this.dataId = init.dataId;
    this.requestId = init.requestId;
    this.method = init.method;
    this.path = init.path;
    this.status = init.status;
    this.code = init.code;
    this.details = init.details;
  }

  /** Worth retrying automatically: connectivity problems, 408, 429 and 5xx. */
  get isRetryable(): boolean {
    if (this.kind === "network" || this.kind === "timeout") {
      return true;
    }
    if (this.kind === "http" && this.status !== undefined) {
      return this.status >= 500 || this.status === 408 || this.status === 429;
    }
    return false;
  }

  /**
   * First place to look. A 2xx body that breaks the contract is a backend
   * issue; a 4xx means the request was rejected — usually frontend state,
   * input or permissions.
   */
  get source(): ErrorSource {
    switch (this.kind) {
      case "network":
      case "timeout":
        return "network";
      case "contract":
        return "backend";
      case "http":
        return this.status !== undefined && this.status >= 500 ? "backend" : "frontend";
      case "unknown":
        return "unknown";
    }
  }

  /** Short reference shown to users and pasted into bug reports. */
  get reference(): string {
    return `${this.dataId} · ${this.requestId}`;
  }

  toJSON(): Record<string, unknown> {
    return {
      name: this.name,
      kind: this.kind,
      source: this.source,
      message: this.message,
      dataId: this.dataId,
      requestId: this.requestId,
      method: this.method,
      path: this.path,
      status: this.status,
      code: this.code,
      details: this.details,
    };
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/**
 * RFC 9457 "problem details" — the error format we propose to the backend.
 * `{ type, title, status, detail, instance, code?, errors? }`
 */
const problemDetailsSchema = z.object({
  title: z.string().optional(),
  detail: z.string().optional(),
  code: z.string().optional(),
  errors: z.unknown().optional(),
});

/** Common envelope fallback: `{ error: { code, message, details } }`. */
const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string().optional(),
    message: z.string().optional(),
    details: z.unknown().optional(),
  }),
});

export interface ParsedErrorBody {
  readonly message: string | undefined;
  readonly code: string | undefined;
  readonly details: unknown;
}

// TODO(OBS-002): agree the error format with the backend developer. RFC 9457 is proposed;
// the envelope branch can be deleted once the contract is fixed.
export function parseErrorBody(body: unknown): ParsedErrorBody {
  const envelope = errorEnvelopeSchema.safeParse(body);
  if (envelope.success) {
    return {
      message: envelope.data.error.message,
      code: envelope.data.error.code,
      details: envelope.data.error.details,
    };
  }

  const problem = problemDetailsSchema.safeParse(body);
  if (problem.success) {
    return {
      message: problem.data.detail ?? problem.data.title,
      code: problem.data.code,
      details: problem.data.errors,
    };
  }

  return {
    message: typeof body === "string" && body.length > 0 ? body.slice(0, 200) : undefined,
    code: undefined,
    details: undefined,
  };
}

/** Compact, value-free description of why a response failed schema validation. */
export function summarizeSchemaIssues(
  error: z.ZodError,
): { path: string; code: string; message: string }[] {
  return error.issues.slice(0, 10).map((issue) => ({
    path: issue.path.map(String).join(".") || "(root)",
    code: issue.code,
    message: issue.message,
  }));
}
