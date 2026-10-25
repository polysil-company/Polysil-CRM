import type { PluginListenerHandle } from "@capacitor/core";
import { z } from "zod";

import {
  isNativeApp,
  PolysilTracking,
  type NativeStartOptions,
} from "@/lib/native/tracking-plugin";

/**
 * TRK-008 · The Duty screen's handle on the native tracker: every answer checked with Zod, as at
 * the API boundary. In a browser every call is a harmless no-op.
 */

export { isNativeApp, type NativeStartOptions };

const permissionState = z.enum(["granted", "denied", "prompt"]);

export const trackingPermissionsSchema = z.object({
  /** Fine location. */
  location: permissionState,
  /** "Allow all the time" (Android 10 and up). */
  background: permissionState,
  /** Notifications (Android 13 and up). */
  notifications: permissionState,
  batteryUnrestricted: z.boolean(),
  gpsOn: z.boolean(),
});
export type TrackingPermissions = z.output<typeof trackingPermissionsSchema>;

export const trackingStatusSchema = z.object({
  onDuty: z.boolean(),
  dutyId: z.string().nullable(),
  since: z.string().nullable(),
  lastUploadAt: z.string().nullable(),
  pendingPoints: z.number().int().nonnegative(),
  /** offline, waiting_for_sign_in, bad_clock, forbidden, location_denied, refused:…; null when all went. */
  lastError: z.string().nullable(),
});
export type TrackingStatus = z.output<typeof trackingStatusSchema>;

const deviceSchema = z.object({ deviceId: z.string(), manufacturer: z.string() });
export type NativeDevice = z.output<typeof deviceSchema>;

const flushSchema = z.object({
  accepted: z.number().int().nonnegative(),
  duplicates: z.number().int().nonnegative(),
  rejected: z.number().int().nonnegative(),
  pending: z.number().int().nonnegative(),
});
export type FlushResult = z.output<typeof flushSchema>;

const serverEndedSchema = trackingStatusSchema.extend({ endReason: z.string().nullish() });

export function getNativeDevice(): Promise<NativeDevice> {
  return PolysilTracking.getDeviceId().then((answer) => deviceSchema.parse(answer));
}

export function checkTrackingPermissions(): Promise<TrackingPermissions> {
  return PolysilTracking.checkPermissions().then((answer) =>
    trackingPermissionsSchema.parse(answer),
  );
}

/** Fine location, then "Allow all the time", then notifications; what was granted comes back. */
export function requestTrackingPermissions(): Promise<TrackingPermissions> {
  return PolysilTracking.requestPermissions().then((answer) =>
    trackingPermissionsSchema.parse(answer),
  );
}

export function openBatterySettings(): Promise<void> {
  return PolysilTracking.openBatterySettings();
}

/** The app's own settings page, or the phone's location switch. */
export function openPhoneSettings(which: "app" | "location"): Promise<void> {
  return PolysilTracking.openSettings({ which });
}

/** TRK-009 · What the native uploader needs of a device token. */
export interface NativeDeviceToken {
  readonly token: string;
  readonly expiresAt: string;
  readonly userId: string;
}

/** TRK-009 · Hands the device token to the native uploader, which keeps it sealed on the phone. */
export function handDeviceTokenToNative(token: NativeDeviceToken): Promise<void> {
  return PolysilTracking.setDeviceToken(token);
}

export function startNativeTracking(options: NativeStartOptions): Promise<void> {
  return PolysilTracking.start(options);
}

export function stopNativeTracking(): Promise<void> {
  return PolysilTracking.stop();
}

/** Upload what waits, now. */
export function flushNativeTracking(): Promise<FlushResult> {
  return PolysilTracking.flush().then((answer) => flushSchema.parse(answer));
}

export function getNativeStatus(): Promise<TrackingStatus> {
  return PolysilTracking.getStatus().then((answer) => trackingStatusSchema.parse(answer));
}

/** Status changes while the screen is open; an answer that doesn't read is skipped. */
export function onNativeStatus(
  listener: (status: TrackingStatus) => void,
): Promise<PluginListenerHandle> {
  return PolysilTracking.addListener("status", (event) => {
    const parsed = trackingStatusSchema.safeParse(event);
    if (parsed.success) listener(parsed.data);
  });
}

/** The server ended the duty (idle after hours, consent withdrawn, deactivated). */
export function onServerEndedDuty(
  listener: (status: TrackingStatus, endReason: string | null) => void,
): Promise<PluginListenerHandle> {
  return PolysilTracking.addListener("serverEndedDuty", (event) => {
    const parsed = serverEndedSchema.safeParse(event);
    if (parsed.success) {
      const { endReason, ...status } = parsed.data;
      listener(status, endReason ?? null);
    }
  });
}
