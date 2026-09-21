"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { sessionQueryOptions } from "@/features/session/api/session.queries";
import type { Session } from "@/features/session/api/session.schemas";
import { can, type Permission } from "@/lib/auth/permissions";

export function useSession(): UseQueryResult<Session> {
  return useQuery(sessionQueryOptions());
}

/**
 * Whether the current user may use a feature. False while the session loads.
 * UI gating only — the backend enforces permissions.
 */
export function useCan(permission: Permission): boolean {
  const { data } = useSession();
  return data !== undefined && can(data.role, permission);
}
