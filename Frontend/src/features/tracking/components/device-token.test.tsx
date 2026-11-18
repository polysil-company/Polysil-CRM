import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DeviceTokenWire } from "@/features/tracking/api/duty.schemas";
import { DeviceTokenMissingError, renewDeviceToken } from "@/features/tracking/native/device-token";
import type { NativeDeviceToken, TrackingStatus } from "@/features/tracking/native/tracking-bridge";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DeviceTokenOnLaunch } from "./device-token-on-launch";

interface Phone {
  native: boolean;
  status: TrackingStatus;
  handed: NativeDeviceToken[];
}

const phone = vi.hoisted((): Phone => ({
  native: true,
  status: {
    onDuty: false,
    dutyId: null,
    since: null,
    lastUploadAt: null,
    pendingPoints: 0,
    lastError: null,
  },
  handed: [],
}));

vi.mock("@/features/tracking/native/use-native-app", () => ({
  useIsNativeApp: () => phone.native,
}));

vi.mock("@/features/tracking/native/tracking-bridge", () => ({
  isNativeApp: () => phone.native,
  getNativeDevice: () => Promise.resolve({ deviceId: "device-1", manufacturer: "Google" }),
  getNativeStatus: () => Promise.resolve(phone.status),
  handDeviceTokenToNative: (token: NativeDeviceToken) => {
    phone.handed.push(token);
    return Promise.resolve();
  },
}));

/** Every `POST /tracking/device-token`: its body and idempotency key. */
function recordTokenRequests(): { deviceId: unknown; key: string | null }[] {
  const seen: { deviceId: unknown; key: string | null }[] = [];
  server.events.on("request:start", ({ request }) => {
    if (!new URL(request.url).pathname.endsWith("/tracking/device-token")) return;
    const key = request.headers.get("Idempotency-Key");
    void request
      .clone()
      .json()
      .then((body: unknown) => {
        const deviceId =
          typeof body === "object" && body !== null && "device_id" in body
            ? body.device_id
            : undefined;
        seen.push({ deviceId, key });
      });
  });
  return seen;
}

function onDuty(): void {
  phone.status = {
    ...phone.status,
    onDuty: true,
    dutyId: "duty-1",
    since: "2026-10-25T09:02:00+05:30",
  };
}

function resetPhone(): void {
  resetMockDb();
  writeMockRole("employee");
  phone.native = true;
  phone.status = {
    onDuty: false,
    dutyId: null,
    since: null,
    lastUploadAt: null,
    pendingPoints: 0,
    lastError: null,
  };
  phone.handed = [];
}

function cleanUp(): void {
  server.events.removeAllListeners();
  writeMockRole("admin");
}

describe("[TRK-009] The device token for the phone's uploads", () => {
  beforeEach(resetPhone);
  afterEach(cleanUp);

  it("asks once for callers that arrive together, and hands the tracker that answer", async () => {
    const requests = recordTokenRequests();

    await Promise.all([renewDeviceToken(), renewDeviceToken()]);

    await waitFor(() => {
      expect(requests).toHaveLength(1);
    });
    expect(requests[0]?.deviceId).toBe("device-1");
    expect(phone.handed).toHaveLength(1);
    expect(phone.handed[0]).toMatchObject({
      token: expect.stringMatching(/^pdt_/),
      userId: mockMeFor("employee").data.id,
    });
  });

  it("hands the expiry over in milliseconds and UTC, which Android reads", async () => {
    server.use(
      http.post(buildApiUrl("/tracking/device-token"), () => {
        const answer: DeviceTokenWire = {
          token: "pdt_from-the-server",
          user_id: mockMeFor("employee").data.id,
          device_id: "device-1",
          expires_at: "2026-11-24T09:02:00.123456+05:30",
        };
        return HttpResponse.json({ data: answer }, { status: 201 });
      }),
    );

    await renewDeviceToken();

    expect(phone.handed[0]?.expiresAt).toBe("2026-11-24T03:32:00.123Z");
  });

  it("asks again, under a new key, once the last call is done", async () => {
    const requests = recordTokenRequests();

    await renewDeviceToken();
    await renewDeviceToken();

    await waitFor(() => {
      expect(requests).toHaveLength(2);
    });
    expect(requests[0]?.key).not.toBe(requests[1]?.key);
    expect(phone.handed).toHaveLength(2);
  });

  it("hands nothing over when the answer carries no token", async () => {
    server.use(
      http.post(buildApiUrl("/tracking/device-token"), () => {
        const answer: DeviceTokenWire = {
          token: null,
          user_id: mockMeFor("employee").data.id,
          device_id: "device-1",
          expires_at: "2026-11-24T09:02:00+05:30",
        };
        return HttpResponse.json({ data: answer }, { status: 201 });
      }),
    );

    await expect(renewDeviceToken()).rejects.toBeInstanceOf(DeviceTokenMissingError);
    expect(phone.handed).toHaveLength(0);
  });

  it("is refused for a role that doesn't track, and hands nothing over", async () => {
    writeMockRole("dealer");

    await expect(renewDeviceToken()).rejects.toMatchObject({ status: 403 });
    expect(phone.handed).toHaveLength(0);
  });
});

describe("[TRK-009] A new device token on each launch of the app", () => {
  beforeEach(resetPhone);
  afterEach(cleanUp);

  it("is asked for when a duty is open", async () => {
    onDuty();
    const requests = recordTokenRequests();

    renderWithProviders(<DeviceTokenOnLaunch />);

    await waitFor(() => {
      expect(phone.handed).toHaveLength(1);
    });
    expect(requests).toHaveLength(1);
  });

  it("isn't asked for off duty, or in a browser", async () => {
    const requests = recordTokenRequests();
    const { unmount } = renderWithProviders(<DeviceTokenOnLaunch />);
    unmount();

    phone.native = false;
    onDuty();
    renderWithProviders(<DeviceTokenOnLaunch />);

    // Give any request a chance to start before checking that none did.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(requests).toHaveLength(0);
    expect(phone.handed).toHaveLength(0);
  });
});
