import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { endDuty, startDuty } from "@/features/tracking/api/duty.api";
import type {
  NativeStartOptions,
  TrackingPermissions,
  TrackingStatus,
} from "@/features/tracking/native/tracking-bridge";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { currentPolicy } from "@/mocks/handlers/policy";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DutyScreen } from "./duty-screen";

interface Phone {
  native: boolean;
  permissions: TrackingPermissions;
  status: TrackingStatus;
  manufacturer: string;
  /** What happened, in order: API calls and tracker calls together. */
  calls: string[];
  started: NativeStartOptions | null;
  statusListener: ((status: TrackingStatus) => void) | null;
  endedListener: ((status: TrackingStatus, reason: string | null) => void) | null;
}

/** The phone, as the tests set it: inside the app or not, its permissions and its tracker. */
const phone = vi.hoisted((): Phone => ({
  native: true,
  permissions: {
    location: "granted",
    background: "granted",
    notifications: "granted",
    batteryUnrestricted: true,
    gpsOn: true,
  },
  status: {
    onDuty: false,
    dutyId: null,
    since: null,
    lastUploadAt: null,
    pendingPoints: 0,
    lastError: null,
  },
  manufacturer: "Google",
  calls: [],
  started: null,
  statusListener: null,
  endedListener: null,
}));

vi.mock("@/features/tracking/native/use-native-app", () => ({
  useIsNativeApp: () => phone.native,
}));

vi.mock("@/features/tracking/native/tracking-bridge", () => ({
  isNativeApp: () => phone.native,
  getNativeDevice: () =>
    Promise.resolve({ deviceId: "device-1", manufacturer: phone.manufacturer }),
  checkTrackingPermissions: () => Promise.resolve(phone.permissions),
  requestTrackingPermissions: vi.fn(() => {
    phone.calls.push("requestPermissions");
    return Promise.resolve(phone.permissions);
  }),
  openBatterySettings: vi.fn(() => {
    phone.calls.push("openBatterySettings");
    return Promise.resolve();
  }),
  openPhoneSettings: vi.fn((which: string) => {
    phone.calls.push(`openSettings:${which}`);
    return Promise.resolve();
  }),
  startNativeTracking: (options: NativeStartOptions) => {
    phone.calls.push("tracker.start");
    phone.started = options;
    phone.status = { ...phone.status, onDuty: true, dutyId: options.dutyId, since: options.since };
    return Promise.resolve();
  },
  stopNativeTracking: () => {
    phone.calls.push("tracker.stop");
    phone.status = { ...phone.status, onDuty: false, dutyId: null, since: null };
    return Promise.resolve();
  },
  flushNativeTracking: () => {
    phone.calls.push("tracker.flush");
    return Promise.resolve({ accepted: 3, duplicates: 0, rejected: 0, pending: 0 });
  },
  getNativeStatus: () => Promise.resolve(phone.status),
  onNativeStatus: (listener: (status: TrackingStatus) => void) => {
    phone.statusListener = listener;
    return Promise.resolve({ remove: () => Promise.resolve() });
  },
  onServerEndedDuty: (listener: (status: TrackingStatus, reason: string | null) => void) => {
    phone.endedListener = listener;
    return Promise.resolve({ remove: () => Promise.resolve() });
  },
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function stubLocation(): void {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: (
        ok: (position: {
          coords: { latitude: number; longitude: number; accuracy: number };
          timestamp: number;
        }) => void,
      ) => {
        ok({
          coords: { latitude: 22.3039, longitude: 70.8022, accuracy: 12 },
          timestamp: Date.now(),
        });
      },
    },
  });
}

/** The person has accepted this version of the consent. */
function consented(role: Role): void {
  mockDb.trackingConsent.set(mockMeFor(role).data.id, currentPolicy().consent_version);
}

/** API calls to the duty endpoints, in order, in the same list as the tracker's calls. */
function recordDutyCalls(): void {
  server.events.on("request:start", ({ request }) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith("/tracking/duty/start")) phone.calls.push("api.start");
    if (path.endsWith("/tracking/duty/end")) phone.calls.push("api.end");
  });
}

function show(): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <DutyScreen />
      <Toaster />
    </>,
  );
  return user;
}

function resetPhone(): void {
  resetMockDb();
  phone.native = true;
  phone.permissions = {
    location: "granted",
    background: "granted",
    notifications: "granted",
    batteryUnrestricted: true,
    gpsOn: true,
  };
  phone.status = {
    onDuty: false,
    dutyId: null,
    since: null,
    lastUploadAt: null,
    pendingPoints: 0,
    lastError: null,
  };
  phone.manufacturer = "Google";
  phone.calls = [];
  phone.started = null;
  stubLocation();
}

function cleanUp(): void {
  server.events.removeAllListeners();
  writeMockRole("admin");
}

describe("[TRK-008] Going on and off duty, through the API", () => {
  beforeEach(resetPhone);
  afterEach(cleanUp);

  it("needs consent, then starts once, answers the open duty again, and ends it", async () => {
    writeMockRole("employee");
    const body = {
      id: "duty-a",
      device_id: "device-1",
      at: "2026-10-22T09:02:00+05:30",
      sent_at: "2026-10-22T09:02:01+05:30",
      lat: 22.3,
      lng: 70.8,
      accuracy_m: 9,
    };
    const refused = await startDuty({ body, idempotencyKey: createRequestId() }).catch(
      (error: unknown) => error,
    );
    expect(isApiError(refused) ? refused.code : null).toBe("consent_required");

    consented("employee");
    const first = await startDuty({ body, idempotencyKey: createRequestId() });
    const again = await startDuty({
      body: { ...body, id: "duty-b" },
      idempotencyKey: createRequestId(),
    });
    // A reinstall mid-duty gets the open session back: use the answer's id.
    expect(again.id).toBe(first.id);

    const ended = await endDuty({
      body: {
        id: first.id,
        at: body.at,
        sent_at: body.sent_at,
        lat: 22.3,
        lng: 70.8,
        accuracy_m: 9,
      },
      idempotencyKey: createRequestId(),
    });
    expect(ended.endReason).toBe("user");
    const missing = await endDuty({
      body: {
        id: "not-mine",
        at: body.at,
        sent_at: body.sent_at,
        lat: 1,
        lng: 1,
        accuracy_m: null,
      },
      idempotencyKey: createRequestId(),
    }).catch((error: unknown) => error);
    expect(isApiError(missing) ? missing.code : null).toBe("duty_not_found");
  });
});

describe("[TRK-008] DutyScreen", () => {
  beforeEach(resetPhone);
  afterEach(cleanUp);

  it("in a browser, says Duty is in the app", async () => {
    phone.native = false;
    signInAs("employee");
    show();
    expect(await screen.findByText("Duty is in the Polysil app")).toBeInTheDocument();
  });

  it("asks for the tracking consent first", async () => {
    signInAs("employee");
    const user = show();
    await user.click(await screen.findByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("button", { name: "Go on duty" })).toBeInTheDocument();
  });

  it("keeps Go on duty off until every permission is done, one card each", async () => {
    phone.permissions = {
      location: "prompt",
      background: "prompt",
      notifications: "granted",
      batteryUnrestricted: false,
      gpsOn: true,
    };
    phone.manufacturer = "Xiaomi";
    signInAs("employee");
    consented("employee");
    const user = show();

    const start = await screen.findByRole("button", { name: "Go on duty" });
    expect(start).toBeDisabled();
    expect(screen.getByText("Finish the steps below first.")).toBeInTheDocument();
    const steps = screen.getByRole("region", { name: "Before duty can start" });
    expect(within(steps).getByRole("heading", { name: "Allow location" })).toBeInTheDocument();
    expect(
      within(steps).getByRole("heading", { name: "Turn battery optimisation off for Polysil" }),
    ).toBeInTheDocument();
    // Autostart is advice, not a blocker.
    expect(screen.getByRole("link", { name: "How to allow it on Xiaomi" })).toHaveAttribute(
      "href",
      "https://dontkillmyapp.com/xiaomi",
    );

    await user.click(within(steps).getByRole("button", { name: "Allow location" }));
    await user.click(within(steps).getByRole("button", { name: "Open the setting" }));
    expect(phone.calls).toEqual(["requestPermissions", "openBatterySettings"]);
  });

  it("goes on duty: the API first, then the tracker with the id the server answered", async () => {
    signInAs("employee");
    consented("employee");
    recordDutyCalls();
    server.use(
      http.post(buildApiUrl("/tracking/duty/start"), () =>
        HttpResponse.json(
          {
            data: {
              id: "server-duty",
              started_at: "2026-10-22T09:02:00+05:30",
              ended_at: null,
              end_reason: null,
              outside_hours: false,
            },
          },
          { status: 201 },
        ),
      ),
    );
    const user = show();
    await user.click(await screen.findByRole("button", { name: "Go on duty" }));

    expect(await screen.findByRole("button", { name: "Go off duty" })).toBeInTheDocument();
    expect(phone.calls).toEqual(["api.start", "tracker.start"]);
    expect(phone.started).toMatchObject({
      dutyId: "server-duty",
      intervalSeconds: 120,
      distanceFilterM: 50,
      maxBatchPoints: 500,
    });
    expect(phone.started?.apiBaseUrl).toMatch(/^https?:\/\/.+\/api\/v1$/);
    expect(screen.getByText(/^On duty since /)).toBeInTheDocument();
  });

  it("goes off duty: upload what waits, end it on the server, then stop the tracker", async () => {
    signInAs("employee");
    consented("employee");
    const started = await startDuty({
      body: {
        id: "duty-on",
        device_id: "device-1",
        at: "2026-10-22T09:02:00+05:30",
        sent_at: "2026-10-22T09:02:00+05:30",
        lat: 22.3,
        lng: 70.8,
        accuracy_m: 9,
      },
      idempotencyKey: createRequestId(),
    });
    phone.status = { ...phone.status, onDuty: true, dutyId: started.id, since: started.startedAt };
    recordDutyCalls();
    const user = show();

    await user.click(await screen.findByRole("button", { name: "Go off duty" }));
    expect(await screen.findByRole("button", { name: "Go on duty" })).toBeInTheDocument();
    expect(phone.calls).toEqual(["tracker.flush", "api.end", "tracker.stop"]);
    await waitFor(() => {
      expect(mockDb.duties.get(mockMeFor("employee").data.id)?.at(-1)?.end_reason).toBe("user");
    });
  });

  it("shows waiting points calmly when offline", async () => {
    phone.status = {
      onDuty: true,
      dutyId: "duty-1",
      since: "2026-10-22T09:02:00+05:30",
      lastUploadAt: null,
      pendingPoints: 42,
      lastError: "offline",
    };
    signInAs("employee");
    consented("employee");
    show();
    const facts = await screen
      .findByRole("list", { name: "Duty today" })
      .catch(() => screen.findByLabelText("Duty today"));
    expect(within(facts).getByText("42")).toBeInTheDocument();
    expect(within(facts).getByText("Not yet")).toBeInTheDocument();
    expect(
      screen.getByText("No connection. Points are kept on the phone and go up when it's back."),
    ).toBeInTheDocument();
  });

  it("says when the server ended the duty", async () => {
    phone.status = {
      ...phone.status,
      onDuty: true,
      dutyId: "duty-1",
      since: "2026-10-22T09:02:00+05:30",
    };
    signInAs("employee");
    consented("employee");
    show();
    await screen.findByRole("button", { name: "Go off duty" });
    await waitFor(() => {
      expect(phone.endedListener).not.toBeNull();
    });
    phone.endedListener?.({ ...phone.status, onDuty: false, dutyId: null, since: null }, "auto");
    expect(await screen.findByText("Duty ended after working hours.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Go on duty" })).toBeInTheDocument();
  });
});
