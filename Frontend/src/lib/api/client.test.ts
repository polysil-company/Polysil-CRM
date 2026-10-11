import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import {
  createLogger,
  registerLogTransport,
  setBrowserLogLevelOverride,
  type LogRecord,
} from "@/lib/logger";
import { server } from "@/mocks/node";

import {
  apiDownload,
  apiRequest,
  registerAccessTokenProvider,
  type AccessTokenProvider,
} from "./client";
import { ApiError } from "./errors";
import { buildApiUrl } from "./url";

const log = createLogger({ file: "lib/api/client.test.ts", dataId: "OBS-002" });
const itemSchema = z.object({ id: z.string(), total: z.number() });
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

async function captureError(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("Expected the request to fail");
}

async function expectApiError(promise: Promise<unknown>): Promise<ApiError> {
  const error = await captureError(promise);
  expect(error).toBeInstanceOf(ApiError);
  if (!(error instanceof ApiError)) {
    throw new Error("Expected an ApiError");
  }
  return error;
}

describe("[OBS-002] apiRequest", () => {
  const records: LogRecord[] = [];
  let unregister = (): void => undefined;

  beforeEach(() => {
    records.length = 0;
    setBrowserLogLevelOverride("debug");
    unregister = registerLogTransport({
      name: "capture",
      write: (record) => {
        records.push(record);
      },
    });
  });

  afterEach(() => {
    unregister();
  });

  const getItem = (
    overrides: { signal?: AbortSignal; timeoutMs?: number } = {},
  ): Promise<unknown> =>
    apiRequest({
      dataId: "OBS-002",
      logger: log,
      fn: "getItem",
      path: "/test/item",
      schema: itemSchema,
      ...overrides,
    });

  it("sends the Data ID and a request ID, logs both directions and returns the parsed body", async () => {
    let received: Headers | undefined;
    server.use(
      http.get(buildApiUrl("/test/item"), ({ request }) => {
        received = request.headers;
        return HttpResponse.json({ id: "a", total: 3 });
      }),
    );

    await expect(getItem()).resolves.toEqual({ id: "a", total: 3 });
    expect(received?.get("x-data-id")).toBe("OBS-002");
    expect(received?.get("x-request-id")).toMatch(UUID);
    expect(records.map((record) => record.message)).toEqual([
      "→ GET /test/item",
      "← GET /test/item 200",
    ]);
    expect(records[1]?.requestId).toBe(received?.get("x-request-id"));
  });

  it("serialises query parameters: arrays repeat, empty values are skipped", async () => {
    let url = "";
    server.use(
      http.get(buildApiUrl("/test/list"), ({ request }) => {
        url = request.url;
        return HttpResponse.json({ id: "a", total: 1 });
      }),
    );

    await apiRequest({
      dataId: "OBS-002",
      logger: log,
      fn: "list",
      path: "/test/list",
      query: { status: ["new", "won"], page: 2, q: "", owner: undefined, archived: null },
      schema: itemSchema,
    });

    const params = new URL(url).searchParams;
    expect(params.getAll("status")).toEqual(["new", "won"]);
    expect(params.get("page")).toBe("2");
    expect(params.has("q")).toBe(false);
    expect(params.has("owner")).toBe(false);
    expect(params.has("archived")).toBe(false);
  });

  it("sends JSON bodies with a content type", async () => {
    let body: unknown;
    let contentType: string | null = null;
    server.use(
      http.post(buildApiUrl("/test/item"), async ({ request }) => {
        body = await request.json();
        contentType = request.headers.get("content-type");
        return HttpResponse.json({ id: "b", total: 1 }, { status: 201 });
      }),
    );

    await apiRequest({
      dataId: "OBS-002",
      logger: log,
      fn: "create",
      method: "POST",
      path: "/test/item",
      body: { name: "Ramesh" },
      schema: itemSchema,
    });

    expect(body).toEqual({ name: "Ramesh" });
    expect(contentType).toBe("application/json");
  });

  it("accepts an empty response when the schema expects nothing", async () => {
    server.use(
      http.delete(buildApiUrl("/test/item"), () => new HttpResponse(null, { status: 204 })),
    );

    await expect(
      apiRequest({
        dataId: "OBS-002",
        logger: log,
        fn: "remove",
        method: "DELETE",
        path: "/test/item",
        schema: z.undefined(),
      }),
    ).resolves.toBeUndefined();
  });

  it("normalises an error envelope (422) into a non-retryable http error", async () => {
    server.use(
      http.get(buildApiUrl("/test/item"), () =>
        HttpResponse.json(
          {
            error: {
              code: "DUPLICATE_PHONE",
              message: "Duplicate phone",
              details: { fields: { phone: "Duplicate" } },
            },
          },
          { status: 422 },
        ),
      ),
    );

    const error = await expectApiError(getItem());

    expect(error).toMatchObject({
      kind: "http",
      status: 422,
      code: "DUPLICATE_PHONE",
      message: "Duplicate phone",
      dataId: "OBS-002",
    });
    expect(error.details).toEqual({ fields: { phone: "Duplicate" } });
    expect(error.isRetryable).toBe(false);
    expect(error.source).toBe("frontend");
    expect(error.reference).toMatch(/^OBS-002 · /);
    expect(records.at(-1)?.level).toBe("warn");
  });

  it("reads RFC 9457 problem details and treats 5xx as a retryable backend error", async () => {
    server.use(
      http.get(buildApiUrl("/test/item"), () =>
        HttpResponse.json(
          { title: "Unavailable", detail: "Database unavailable", code: "DB_DOWN" },
          { status: 503 },
        ),
      ),
    );

    const error = await expectApiError(getItem());

    expect(error).toMatchObject({
      kind: "http",
      status: 503,
      code: "DB_DOWN",
      message: "Database unavailable",
    });
    expect(error.isRetryable).toBe(true);
    expect(error.source).toBe("backend");
    expect(records.at(-1)?.level).toBe("error");
  });

  it("flags a 2xx body that breaks the schema as a CONTRACT_VIOLATION", async () => {
    server.use(
      http.get(buildApiUrl("/test/item"), () => HttpResponse.json({ id: 7, total: "three" })),
    );

    const error = await expectApiError(getItem());

    expect(error).toMatchObject({ kind: "contract", code: "CONTRACT_VIOLATION", status: 200 });
    expect(error.source).toBe("backend");
    expect(error.isRetryable).toBe(false);
    expect(error.details).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: "id" }),
        expect.objectContaining({ path: "total" }),
      ]),
    );
    expect(records.at(-1)).toMatchObject({
      level: "error",
      message: "✕ GET /test/item CONTRACT_VIOLATION",
    });
  });

  it("reports a failed connection as a retryable network error", async () => {
    server.use(http.get(buildApiUrl("/test/item"), () => HttpResponse.error()));

    const error = await expectApiError(getItem());

    expect(error.kind).toBe("network");
    expect(error.isRetryable).toBe(true);
    expect(error.source).toBe("network");
  });

  it("times out a response that takes too long", async () => {
    server.use(
      http.get(buildApiUrl("/test/item"), async () => {
        await delay(250);
        return HttpResponse.json({ id: "a", total: 1 });
      }),
    );

    const error = await expectApiError(getItem({ timeoutMs: 20 }));

    expect(error.kind).toBe("timeout");
  });

  it("re-throws a caller's cancellation as AbortError so TanStack Query can ignore it", async () => {
    server.use(
      http.get(buildApiUrl("/test/item"), async () => {
        await delay(250);
        return HttpResponse.json({ id: "a", total: 1 });
      }),
    );
    const controller = new AbortController();

    const pending = getItem({ signal: controller.signal });
    controller.abort();
    const error = await captureError(pending);

    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ name: "AbortError" });
    expect(records.at(-1)).toMatchObject({ level: "debug", message: "✕ GET /test/item cancelled" });
  });
});

describe("[AUTH-004] apiRequest authentication", () => {
  const records: LogRecord[] = [];
  let unregister = (): void => undefined;

  function registerProvider(token: string | null = "stale"): AccessTokenProvider {
    const provider: AccessTokenProvider = {
      getAccessToken: vi.fn(({ forceRefresh }: { readonly forceRefresh: boolean }) =>
        Promise.resolve(token === null ? null : forceRefresh ? "fresh" : token),
      ),
      peekAccessToken: vi.fn(() => token),
      onSessionRejected: vi.fn(),
    };
    registerAccessTokenProvider(provider);
    return provider;
  }

  beforeEach(() => {
    records.length = 0;
    setBrowserLogLevelOverride("debug");
    unregister = registerLogTransport({
      name: "capture",
      write: (record) => {
        records.push(record);
      },
    });
  });

  afterEach(() => {
    registerAccessTokenProvider(null);
    unregister();
  });

  const getItem = (auth?: "required" | "optional" | "none"): Promise<unknown> =>
    apiRequest({
      dataId: "AUTH-002",
      logger: log,
      fn: "getItem",
      path: "/test/item",
      schema: itemSchema,
      ...(auth === undefined ? {} : { auth }),
    });

  it("sends the access token, and retries once with a refreshed one after a 401", async () => {
    const provider = registerProvider();
    const seen: (string | null)[] = [];
    server.use(
      http.get(buildApiUrl("/test/item"), ({ request }) => {
        const authorization = request.headers.get("authorization");
        seen.push(authorization);
        return authorization === "Bearer fresh"
          ? HttpResponse.json({ id: "a", total: 1 })
          : HttpResponse.json({ error: { code: "unauthenticated" } }, { status: 401 });
      }),
    );

    await expect(getItem()).resolves.toEqual({ id: "a", total: 1 });

    expect(seen).toEqual(["Bearer stale", "Bearer fresh"]);
    expect(provider.getAccessToken).toHaveBeenLastCalledWith({ forceRefresh: true });
    expect(provider.onSessionRejected).not.toHaveBeenCalled();
    expect(records.map((record) => record.message)).toContain(
      "↻ GET /test/item 401, refreshing the session",
    );
  });

  it("ends the session when the refreshed token is refused as well", async () => {
    const provider = registerProvider();
    server.use(
      http.get(buildApiUrl("/test/item"), () =>
        HttpResponse.json({ error: { code: "unauthenticated" } }, { status: 401 }),
      ),
    );

    const error = await expectApiError(getItem());

    expect(error).toMatchObject({ status: 401, code: "unauthenticated" });
    expect(provider.onSessionRejected).toHaveBeenCalledOnce();
  });

  it("fails without sending anything when there is no session", async () => {
    registerProvider(null);
    const handler = vi.fn(() => HttpResponse.json({ id: "a", total: 1 }));
    server.use(http.get(buildApiUrl("/test/item"), handler));

    const error = await expectApiError(getItem());

    expect(error).toMatchObject({ kind: "http", status: 401, code: "unauthenticated" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("sends no token and never refreshes for the sign-in endpoints", async () => {
    const provider = registerProvider();
    let authorization: string | null = "unset";
    server.use(
      http.get(buildApiUrl("/test/item"), ({ request }) => {
        authorization = request.headers.get("authorization");
        return HttpResponse.json({ error: { code: "invalid_credentials" } }, { status: 401 });
      }),
    );

    const error = await expectApiError(getItem("none"));

    expect(error.code).toBe("invalid_credentials");
    expect(authorization).toBeNull();
    expect(provider.getAccessToken).not.toHaveBeenCalled();
  });

  it("sends the token in memory for optional authentication, without refreshing", async () => {
    const provider = registerProvider();
    let authorization: string | null = null;
    server.use(
      http.get(buildApiUrl("/test/item"), ({ request }) => {
        authorization = request.headers.get("authorization");
        return HttpResponse.json({ id: "a", total: 1 });
      }),
    );

    await getItem("optional");

    expect(authorization).toBe("Bearer stale");
    expect(provider.getAccessToken).not.toHaveBeenCalled();
  });

  it("sends an Idempotency-Key on mutations, except the keyless /auth ones", async () => {
    const keys: Record<string, string | null> = {};
    server.use(
      http.post(buildApiUrl("/test/item"), ({ request }) => {
        keys.item = request.headers.get("idempotency-key");
        return HttpResponse.json({ id: "a", total: 1 });
      }),
      http.post(buildApiUrl("/auth/login"), ({ request }) => {
        keys.login = request.headers.get("idempotency-key");
        return HttpResponse.json({ id: "a", total: 1 });
      }),
      http.post(buildApiUrl("/auth/password"), ({ request }) => {
        keys.password = request.headers.get("idempotency-key");
        return HttpResponse.json({ id: "a", total: 1 });
      }),
      http.get(buildApiUrl("/test/item"), ({ request }) => {
        keys.read = request.headers.get("idempotency-key");
        return HttpResponse.json({ id: "a", total: 1 });
      }),
    );

    const post = (path: "/test/item" | "/auth/login" | "/auth/password"): Promise<unknown> =>
      apiRequest({
        dataId: "AUTH-002",
        logger: log,
        fn: "post",
        method: "POST",
        path,
        schema: itemSchema,
      });
    await post("/test/item");
    await post("/auth/login");
    await post("/auth/password");
    await getItem("none");

    expect(keys.item).toMatch(UUID);
    // Login, OTP, refresh and logout take no key; changing a password needs one (AUTH-007).
    expect(keys.login).toBeNull();
    expect(keys.password).toMatch(UUID);
    expect(keys.read).toBeNull();
  });

  it("keeps sensitive request and response bodies out of the logs", async () => {
    server.use(
      http.post(buildApiUrl("/test/item"), () => HttpResponse.json({ id: "tok-9f2c", total: 1 })),
    );

    await apiRequest({
      dataId: "AUTH-001",
      logger: log,
      fn: "verify",
      method: "POST",
      path: "/test/item",
      body: { code: "482913" },
      schema: itemSchema,
      auth: "none",
      sensitive: true,
    });

    const logged = JSON.stringify(records);
    expect(logged).not.toContain("482913");
    expect(logged).not.toContain("tok-9f2c");
    expect(logged).toContain("[REDACTED]");
  });
});

describe("[OBS-002] apiDownload", () => {
  afterEach(() => {
    registerAccessTokenProvider(null);
  });

  const download = (): ReturnType<typeof apiDownload> =>
    apiDownload({
      dataId: "TASK-008",
      logger: log,
      fn: "exportTasks",
      path: "/tasks/export",
      query: { status: ["open"], lead_id: null },
    });

  it("returns the file and the name the backend gave it, with the token and the Data ID", async () => {
    registerAccessTokenProvider({
      getAccessToken: () => Promise.resolve("token-1"),
      peekAccessToken: () => "token-1",
      onSessionRejected: vi.fn(),
    });
    let headers: Headers | undefined;
    let url: URL | undefined;
    server.use(
      http.get(buildApiUrl("/tasks/export"), ({ request }) => {
        headers = request.headers;
        url = new URL(request.url);
        return new HttpResponse("PK-xlsx", {
          headers: {
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "content-disposition": 'attachment; filename="tasks-2026-10-04.xlsx"',
          },
        });
      }),
    );

    const file = await download();

    expect(file.filename).toBe("tasks-2026-10-04.xlsx");
    expect(await file.blob.text()).toBe("PK-xlsx");
    expect(headers?.get("authorization")).toBe("Bearer token-1");
    expect(headers?.get("x-data-id")).toBe("TASK-008");
    expect(url?.searchParams.getAll("status")).toEqual(["open"]);
  });

  it("has no name when the backend gives none", async () => {
    server.use(http.get(buildApiUrl("/tasks/export"), () => new HttpResponse("x")));

    await expect(download()).resolves.toMatchObject({ filename: null });
  });

  it("reads the error envelope of a refused export as an ApiError", async () => {
    server.use(
      http.get(buildApiUrl("/tasks/export"), () =>
        HttpResponse.json(
          { error: { code: "export_too_large", message: "More than 5000 rows." } },
          { status: 422 },
        ),
      ),
    );

    const error = await expectApiError(download());

    expect(error).toMatchObject({ status: 422, code: "export_too_large" });
  });
});
