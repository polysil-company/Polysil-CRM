import { describe, expect, it } from "vitest";

import {
  checkTrackingPermissions,
  flushNativeTracking,
  getNativeStatus,
  isNativeApp,
  onNativeStatus,
  startNativeTracking,
  stopNativeTracking,
  trackingStatusSchema,
} from "./tracking-bridge";

describe("[TRK-008] The native tracker in a browser", () => {
  it("is a harmless no-op", async () => {
    expect(isNativeApp()).toBe(false);
    expect(await getNativeStatus()).toMatchObject({ onDuty: false, pendingPoints: 0 });
    expect(await checkTrackingPermissions()).toMatchObject({ location: "denied", gpsOn: false });
    await expect(
      startNativeTracking({
        dutyId: "d-1",
        since: "2026-10-22T09:02:00+05:30",
        intervalSeconds: 120,
        distanceFilterM: 50,
        maxBatchPoints: 500,
        apiBaseUrl: "https://example.test/api/v1",
      }),
    ).resolves.toBeUndefined();
    await expect(stopNativeTracking()).resolves.toBeUndefined();
    expect(await flushNativeTracking()).toEqual({
      accepted: 0,
      duplicates: 0,
      rejected: 0,
      pending: 0,
    });
    const handle = await onNativeStatus(() => undefined);
    await expect(handle.remove()).resolves.toBeUndefined();
  });
});

describe("[TRK-008] The tracker's status as Android sends it", () => {
  it("reads a field Android left out as empty: off duty, it sends no duty, time or error", () => {
    // org.json drops a key whose value is null, so this is the whole answer off duty.
    expect(trackingStatusSchema.parse({ onDuty: false, pendingPoints: 0 })).toEqual({
      onDuty: false,
      dutyId: null,
      since: null,
      lastUploadAt: null,
      pendingPoints: 0,
      lastError: null,
    });
  });

  it("keeps the fields Android sends", () => {
    expect(
      trackingStatusSchema.parse({
        onDuty: true,
        dutyId: "duty-1",
        since: "2026-10-30T09:02:00.000+05:30",
        pendingPoints: 3,
      }),
    ).toMatchObject({
      dutyId: "duty-1",
      since: "2026-10-30T09:02:00.000+05:30",
      lastUploadAt: null,
    });
  });
});
