import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { buildApiUrl } from "@/lib/api/url";
import { MOCK_STAFF_PASSWORD } from "@/lib/dev/mock-settings";
import { createLogger } from "@/lib/logger";
import { server } from "@/mocks/node";

const log = createLogger({ file: "lib/auth/session-store.test.ts", dataId: "AUTH-004" });
const meSchema = z.object({ data: z.object({ full_name: z.string() }) });

/** A fresh copy of the store and the API client, as after a page load. */
async function loadPage() {
  vi.resetModules();
  const store = await import("./session-store");
  const { apiRequest } = await import("@/lib/api/client");
  const { tokenResponseSchema } = await import("./tokens");

  const signIn = async (): Promise<void> => {
    const tokens = await apiRequest({
      dataId: "AUTH-003",
      logger: log,
      fn: "signIn",
      method: "POST",
      path: "/auth/login",
      body: { email: "asha@polysil.in", password: MOCK_STAFF_PASSWORD },
      schema: tokenResponseSchema,
      auth: "none",
    });
    store.acceptSessionTokens(tokens);
  };

  const fetchMe = () =>
    apiRequest({
      dataId: "AUTH-002",
      logger: log,
      fn: "fetchMe",
      path: "/auth/me",
      schema: meSchema,
    });

  return { store, signIn, fetchMe };
}

function countRequests(pathSuffix: string): { count: () => number } {
  let count = 0;
  server.events.on("request:start", ({ request }) => {
    if (new URL(request.url).pathname.endsWith(pathSuffix)) {
      count += 1;
    }
  });
  return { count: () => count };
}

describe("[AUTH-004] session store", () => {
  afterEach(() => {
    server.events.removeAllListeners();
    document.cookie = "polysil_session=; Max-Age=0; Path=/";
  });

  it("starts signed out on a browser that never signed in, without calling the backend", async () => {
    const { store } = await loadPage();
    const requests = countRequests("");

    store.bootstrapSession();

    expect(store.getAuthSnapshot()).toEqual({ status: "signed-out", endReason: null, error: null });
    expect(requests.count()).toBe(0);
  });

  it("signs in, marks the browser for proxy.ts and sends the token", async () => {
    const { store, signIn, fetchMe } = await loadPage();

    await signIn();

    expect(store.getAuthSnapshot().status).toBe("signed-in");
    expect(document.cookie).toContain("polysil_session=1");
    await expect(fetchMe()).resolves.toEqual({ data: { full_name: "Aarav Desai" } });
  });

  it("refreshes and retries once when the backend rejects the token", async () => {
    const { store, signIn, fetchMe } = await loadPage();
    await signIn();
    const refreshes = countRequests("/auth/refresh");
    server.use(
      http.get(
        buildApiUrl("/auth/me"),
        () => HttpResponse.json({ error: { code: "unauthenticated" } }, { status: 401 }),
        { once: true },
      ),
    );

    await expect(fetchMe()).resolves.toEqual({ data: { full_name: "Aarav Desai" } });

    expect(refreshes.count()).toBe(1);
    expect(store.getAuthSnapshot().status).toBe("signed-in");
  });

  it("ends the session when the refresh cookie is no longer accepted", async () => {
    const { store, signIn, fetchMe } = await loadPage();
    await signIn();
    // The backend revoked the session: its refresh token is gone.
    window.localStorage.removeItem("polysil:mock-auth-refresh");

    await expect(fetchMe()).rejects.toMatchObject({ status: 401 });

    expect(store.getAuthSnapshot()).toEqual({
      status: "signed-out",
      endReason: "session-ended",
      error: null,
    });
    expect(document.cookie).not.toContain("polysil_session=1");
  });

  it("shares one refresh between callers that arrive together", async () => {
    const { store, signIn } = await loadPage();
    await signIn();
    const refreshes = countRequests("/auth/refresh");

    const [first, second] = await Promise.all([
      store.refreshAccessToken(),
      store.refreshAccessToken(),
    ]);

    expect(first).toBe(second);
    expect(refreshes.count()).toBe(1);
  });

  it("restores the session after a reload from the refresh cookie", async () => {
    const firstPage = await loadPage();
    await firstPage.signIn();

    const { store, fetchMe } = await loadPage();
    store.bootstrapSession();

    expect(store.getAuthSnapshot().status).toBe("checking");
    await vi.waitFor(() => {
      expect(store.getAuthSnapshot().status).toBe("signed-in");
    });
    await expect(fetchMe()).resolves.toEqual({ data: { full_name: "Aarav Desai" } });
  });

  it("reports an unreachable backend instead of signing out, and recovers on retry", async () => {
    const firstPage = await loadPage();
    await firstPage.signIn();
    server.use(http.post(buildApiUrl("/auth/refresh"), () => HttpResponse.error(), { once: true }));

    const { store } = await loadPage();
    store.bootstrapSession();

    await vi.waitFor(() => {
      expect(store.getAuthSnapshot().status).toBe("unreachable");
    });
    expect(store.getAuthSnapshot().error).toMatchObject({ kind: "network" });

    store.retrySessionCheck();
    await vi.waitFor(() => {
      expect(store.getAuthSnapshot().status).toBe("signed-in");
    });
  });

  it("records a deliberate sign-out", async () => {
    const { store, signIn } = await loadPage();
    await signIn();

    store.endSession("signed-out");

    expect(store.getAuthSnapshot()).toEqual({
      status: "signed-out",
      endReason: "signed-out",
      error: null,
    });
  });
});
