"use client";

import { useDealerTasksOn } from "@/features/tasks/hooks/use-dealer-tasks";

import type { NavGate } from "./navigation";

/** The nav gates open for the signed-in user (see `NavItem.gate`). */
export function useNavGates(): ReadonlySet<NavGate> {
  const dealerTasks = useDealerTasksOn();
  return new Set<NavGate>(dealerTasks ? ["dealer-tasks"] : []);
}
