import { Capacitor, registerPlugin, type PluginListenerHandle } from "@capacitor/core";

/**
 * TRK-008 · The Android app's native tracker (`mobile/android/…/tracking/TrackingPlugin.kt`),
 * registered once here. Its answers are `unknown` until `features/tracking/native` checks them with
 * Zod. On the web every call is a no-op, and nothing shows that would call it.
 */

export interface NativeStartOptions {
  /** The id `POST /tracking/duty/start` answered, which may differ from the one sent. */
  readonly dutyId: string;
  /** When the duty started, as the server answered it. */
  readonly since: string;
  readonly intervalSeconds: number;
  readonly distanceFilterM: number;
  readonly maxBatchPoints: number;
  /** The API's origin and prefix, "https://…/api/v1", for the native uploads. */
  readonly apiBaseUrl: string;
}

export interface PolysilTrackingPlugin {
  getDeviceId(): Promise<unknown>;
  checkPermissions(): Promise<unknown>;
  requestPermissions(): Promise<unknown>;
  openBatterySettings(): Promise<void>;
  openSettings(options: { readonly which: "app" | "location" }): Promise<void>;
  /** Only `lib/auth/session-store.ts` calls this: the one place a token leaves the API client. */
  setAccessToken(options: { readonly token: string; readonly expiresAt: string }): Promise<void>;
  start(options: NativeStartOptions): Promise<void>;
  stop(): Promise<void>;
  flush(): Promise<unknown>;
  getStatus(): Promise<unknown>;
  addListener(
    eventName: "status" | "serverEndedDuty",
    listener: (event: unknown) => void,
  ): Promise<PluginListenerHandle>;
}

const OFF_DUTY = {
  onDuty: false,
  dutyId: null,
  since: null,
  lastUploadAt: null,
  pendingPoints: 0,
  lastError: null,
};

/** What the plugin answers in a browser: nothing to track, nothing to grant. */
const webTracker: PolysilTrackingPlugin = {
  getDeviceId: () => Promise.resolve({ deviceId: "", manufacturer: "" }),
  checkPermissions: () =>
    Promise.resolve({
      location: "denied",
      background: "denied",
      notifications: "denied",
      batteryUnrestricted: false,
      gpsOn: false,
    }),
  requestPermissions: () =>
    Promise.resolve({
      location: "denied",
      background: "denied",
      notifications: "denied",
      batteryUnrestricted: false,
      gpsOn: false,
    }),
  openBatterySettings: () => Promise.resolve(),
  openSettings: () => Promise.resolve(),
  setAccessToken: () => Promise.resolve(),
  start: () => Promise.resolve(),
  stop: () => Promise.resolve(),
  flush: () => Promise.resolve({ accepted: 0, duplicates: 0, rejected: 0, pending: 0 }),
  getStatus: () => Promise.resolve(OFF_DUTY),
  addListener: () => Promise.resolve({ remove: () => Promise.resolve() }),
};

export const PolysilTracking = registerPlugin<PolysilTrackingPlugin>("PolysilTracking", {
  web: webTracker,
});

/** True inside the Android app; false in any browser. */
export function isNativeApp(): boolean {
  return Capacitor.isNativePlatform();
}
