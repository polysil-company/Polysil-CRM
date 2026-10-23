import { describe, expect, it } from "vitest";

import {
  checkTrackingPermissions,
  flushNativeTracking,
  getNativeStatus,
  isNativeApp,
  onNativeStatus,
  startNativeTracking,
  stopNativeTracking,
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
