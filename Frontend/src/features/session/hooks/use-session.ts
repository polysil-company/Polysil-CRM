"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { sessionQueryOptions } from "@/features/session/api/session.queries";
import type { Session } from "@/features/session/api/session.schemas";
import { can, canApprove, type ModuleCode, type PermissionAction } from "@/lib/auth/permissions";

export function useSession(): UseQueryResult<Session> {
  return useQuery(sessionQueryOptions());
}

/**
 * Whether the current user may take `action` in `module`. False while the session loads.
 * UI gating only — the backend enforces permissions.
 */
export function useCan(module: ModuleCode, action: PermissionAction = "view"): boolean {
  const { data } = useSession();
  return data !== undefined && can(data.permissions, module, action);
}

/** Whether the current user decides approvals (orders or quotation discounts). False while loading. */
export function useCanApprove(): boolean {
  const { data } = useSession();
  return data !== undefined && canApprove(data.permissions);
}

/**
 * Whether the signed-in user is staff, not a channel partner's user. False while loading, so
 * a staff-only control never flashes for a partner. For what the backend keeps from partners
 * whatever their permissions say: QR code writes, lead scores, duplicate review (walk F-1, F-8).
 */
export function useIsStaff(): boolean {
  const { data } = useSession();
  return data?.userType === "staff";
}
