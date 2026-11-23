import { issueDeviceToken } from "@/features/tracking/api/duty.api";
import { createRequestId } from "@/lib/api/request-id";
import { createLogger } from "@/lib/logger";

import { getNativeDevice, handDeviceTokenToNative } from "./tracking-bridge";

const log = createLogger({ file: "features/tracking/native/device-token.ts", dataId: "TRK-009" });

/** The token answer had no token: a replay, which never carries it. Ask again with a new key. */
export class DeviceTokenMissingError extends Error {
  constructor() {
    super("The device token answer carried no token");
    this.name = "DeviceTokenMissingError";
  }
}

let inFlight: Promise<void> | null = null;

async function issueAndHandOver(): Promise<void> {
  const { deviceId } = await getNativeDevice();
  const issued = await issueDeviceToken({ deviceId, idempotencyKey: createRequestId() });
  if (issued.token === null) throw new DeviceTokenMissingError();
  await handDeviceTokenToNative({
    token: issued.token,
    // Milliseconds and "Z": the server may send microseconds, which Android's parser misreads.
    expiresAt: new Date(issued.expiresAt).toISOString(),
    userId: issued.userId,
  });
  log.info("renewDeviceToken", "The phone has a new device token", {
    context: { expiresAt: issued.expiresAt },
  });
}

/**
 * TRK-009 · Gets the phone a device token (BE-032) and hands it to the native uploader, so points
 * go up while the app is closed. Called after duty start and on every launch while a duty is open
 * (contract §1 step 3a).
 *
 * One call at a time: a caller arriving while one runs shares it, so the native side only ever
 * gets the newest answer. Each call uses a new idempotency key, since the server never replays a
 * token.
 */
export function renewDeviceToken(): Promise<void> {
  inFlight ??= issueAndHandOver().finally(() => {
    inFlight = null;
  });
  return inFlight;
}
