"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { nativeStatusQueryOptions } from "@/features/tracking/api/native.queries";
import { renewDeviceToken } from "@/features/tracking/native/device-token";
import { useIsNativeApp } from "@/features/tracking/native/use-native-app";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/tracking/components/device-token-on-launch.tsx",
  dataId: "TRK-009",
});

/**
 * TRK-009 · On every launch of the Android app while a duty is open, a fresh device token for the
 * native uploader (contract §1 step 3a). The old one may have died meanwhile: signed out, signed
 * out everywhere, a password reset, or 30 days. Renders nothing; in a browser it does nothing.
 */
export function DeviceTokenOnLaunch(): null {
  const native = useIsNativeApp();
  const status = useQuery({ ...nativeStatusQueryOptions(), enabled: native });
  const onDuty = status.data?.onDuty === true;
  const renewed = useRef(false);

  // A side effect of the launch, not data for the screen: nothing renders from it.
  useEffect(() => {
    if (!native || !onDuty || renewed.current) return;
    renewed.current = true;
    renewDeviceToken().catch((error: unknown) => {
      // The points stay on the phone; they go up once a token arrives.
      log.warn("renewOnLaunch", "No device token on this launch", { error });
    });
  }, [native, onDuty]);

  return null;
}
