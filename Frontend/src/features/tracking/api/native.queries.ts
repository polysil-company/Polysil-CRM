import { queryOptions } from "@tanstack/react-query";

import {
  checkTrackingPermissions,
  getNativeDevice,
  getNativeStatus,
} from "@/features/tracking/native/tracking-bridge";

import { trackingKeys } from "./tracking.queries";

/** TRK-008 · The native tracker's state, read like any other source the screens show. */
export const nativeKeys = {
  all: [...trackingKeys.all, "native"] as const,
  status: () => [...nativeKeys.all, "status"] as const,
  permissions: () => [...nativeKeys.all, "permissions"] as const,
  device: () => [...nativeKeys.all, "device"] as const,
};

/** On duty or not, the last upload, and the points waiting. Events keep it current. */
export function nativeStatusQueryOptions() {
  return queryOptions({
    queryKey: nativeKeys.status(),
    queryFn: getNativeStatus,
    meta: { dataId: "TRK-008" },
  });
}

/** Read again whenever the app comes back from a settings page. */
export function nativePermissionsQueryOptions() {
  return queryOptions({
    queryKey: nativeKeys.permissions(),
    queryFn: checkTrackingPermissions,
    refetchOnWindowFocus: "always",
    meta: { dataId: "TRK-008" },
  });
}

export function nativeDeviceQueryOptions() {
  return queryOptions({
    queryKey: nativeKeys.device(),
    queryFn: getNativeDevice,
    staleTime: Number.POSITIVE_INFINITY,
    meta: { dataId: "TRK-008" },
  });
}
