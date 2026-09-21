import { afterEach, describe, expect, it, vi } from "vitest";

import { toUserFacingError } from "./error-messages";
import { ApiError, parseErrorBody, type ApiErrorInit } from "./errors";
import { createRequestId } from "./request-id";
import { buildApiUrl } from "./url";

function apiError(init: Partial<ApiErrorInit>): ApiError {
  return new ApiError({
    kind: "http",
    message: "failed",
    dataId: "LEAD-001",
    requestId: "req-1",
    method: "GET",
    path: "/leads",
    ...init,
  });
}

describe("[OBS-002] buildApiUrl", () => {
  it("joins an absolute base and a path", () => {
    expect(buildApiUrl("/leads", undefined, "https://api.example.com/v1")).toBe(
      "https://api.example.com/v1/leads",
    );
  });

  it("supports a same-origin base", () => {
    expect(buildApiUrl("/leads", { page: 2 }, "/api/v1")).toBe("/api/v1/leads?page=2");
  });

  it("repeats arrays, skips empty values and encodes the rest", () => {
    expect(
      buildApiUrl(
        "/leads",
        { status: ["new", "won"], q: "Patel & Sons", owner: "", x: null },
        "/api",
      ),
    ).toBe("/api/leads?status=new&status=won&q=Patel+%26+Sons");
  });
});

describe("[OBS-002] createRequestId", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

  it("creates UUID v4 values", () => {
    expect(createRequestId()).toMatch(UUID);
    expect(createRequestId()).not.toBe(createRequestId());
  });

  it("falls back to getRandomValues where randomUUID is unavailable (insecure origins)", () => {
    const { getRandomValues } = globalThis.crypto;
    vi.stubGlobal("crypto", { getRandomValues: getRandomValues.bind(globalThis.crypto) });

    expect(createRequestId()).toMatch(UUID);
  });
});

describe("[OBS-002] parseErrorBody", () => {
  it("reads the envelope format", () => {
    expect(parseErrorBody({ error: { code: "X", message: "Nope", details: { a: 1 } } })).toEqual({
      code: "X",
      message: "Nope",
      details: { a: 1 },
    });
  });

  it("reads problem details, preferring detail over title", () => {
    expect(parseErrorBody({ title: "Bad", detail: "Very bad", errors: ["e"] })).toEqual({
      code: undefined,
      message: "Very bad",
      details: ["e"],
    });
  });

  it("falls back to a short plain-text body", () => {
    expect(parseErrorBody("Gateway timeout").message).toBe("Gateway timeout");
    expect(parseErrorBody(undefined).message).toBeUndefined();
  });
});

describe("[OBS-002] toUserFacingError", () => {
  it("never shows raw server messages and always carries the reference", () => {
    const view = toUserFacingError(
      apiError({ status: 500, message: "SQL syntax error near SELECT" }),
    );

    expect(view.title).toBe("Something went wrong on our side");
    expect(view.description).not.toContain("SQL");
    expect(view.reference).toBe("LEAD-001 · req-1");
    expect(view.retryable).toBe(true);
  });

  it.each([
    { init: { kind: "network" as const }, title: "You appear to be offline", retryable: true },
    { init: { kind: "timeout" as const }, title: "This is taking too long", retryable: true },
    {
      init: { kind: "contract" as const },
      title: "We received data we couldn't read",
      retryable: false,
    },
    { init: { status: 401 }, title: "Your session has ended", retryable: false },
    { init: { status: 403 }, title: "You don't have access to this", retryable: false },
    { init: { status: 404 }, title: "Not found", retryable: false },
    { init: { status: 422 }, title: "Some details need attention", retryable: false },
    { init: { status: 429 }, title: "Too many requests", retryable: true },
  ])("maps $title", ({ init, title, retryable }) => {
    const view = toUserFacingError(apiError(init));
    expect(view.title).toBe(title);
    expect(view.retryable).toBe(retryable);
  });

  it("uses generic copy for unexpected errors", () => {
    expect(toUserFacingError(new TypeError("x is undefined"))).toEqual({
      title: "Something went wrong",
      description: "An unexpected problem stopped this from loading. Try again.",
      reference: undefined,
      retryable: true,
    });
  });
});
