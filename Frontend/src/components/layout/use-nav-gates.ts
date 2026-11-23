"use client";

import { useDealerTasksOn } from "@/features/tasks/hooks/use-dealer-tasks";
import { useIsNativeApp } from "@/features/tracking/native/use-native-app";

import type { NavGate } from "./navigation";

/** The nav gates open for the signed-in user (see `NavItem.gate`). */
export function useNavGates(): ReadonlySet<NavGate> {
  const dealerTasks = useDealerTasksOn();
  const nativeApp = useIsNativeApp();
  return new Set<NavGate>([
    ...(dealerTasks ? (["dealer-tasks"] as const) : []),
    ...(nativeApp ? (["native-app"] as const) : []),
  ]);
}
