"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { leadKeys } from "@/features/leads/api/leads.queries";

import {
  createUser,
  deleteUser,
  handOver,
  patchUser,
  revokeSessions,
  setTemporaryPassword,
  unlockUser,
} from "./users.api";
import { userKeys } from "./users.queries";
import type { HandoverResult, UserDetail } from "./users.schemas";

function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: userKeys.all });
  };
}

/** ADMN-003 · Add a staff member or a partner user. */
export function useCreateUser(): UseMutationResult<
  UserDetail,
  Error,
  Parameters<typeof createUser>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...userKeys.all, "create"],
    mutationFn: createUser,
    meta: { dataId: "ADMN-003" },
    onSuccess: refresh,
  });
}

/** ADMN-004 · Correct a person, or deactivate or reactivate them. */
export function usePatchUser(): UseMutationResult<
  UserDetail,
  Error,
  Parameters<typeof patchUser>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...userKeys.all, "patch"],
    mutationFn: patchUser,
    meta: { dataId: "ADMN-004" },
    onSuccess: refresh,
  });
}

/** ADMN-005 · A new temporary password. */
export function useSetTemporaryPassword(): UseMutationResult<
  { sessionsRevoked: number },
  Error,
  Parameters<typeof setTemporaryPassword>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...userKeys.all, "password"],
    mutationFn: setTemporaryPassword,
    meta: { dataId: "ADMN-005" },
    onSuccess: refresh,
  });
}

/** ADMN-005 · Sign a person out everywhere. */
export function useRevokeSessions(): UseMutationResult<
  { sessionsRevoked: number },
  Error,
  Parameters<typeof revokeSessions>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...userKeys.all, "revoke"],
    mutationFn: revokeSessions,
    meta: { dataId: "ADMN-005" },
    onSuccess: refresh,
  });
}

/** ADMN-005 · Clear a sign-in lockout. */
export function useUnlockUser(): UseMutationResult<
  { wasLocked: boolean },
  Error,
  Parameters<typeof unlockUser>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...userKeys.all, "unlock"],
    mutationFn: unlockUser,
    meta: { dataId: "ADMN-005" },
    onSuccess: refresh,
  });
}

/** ADMN-006 · Hand a leaver's open leads and tasks over; the leads change owner too. */
export function useHandOver(): UseMutationResult<
  HandoverResult,
  Error,
  Parameters<typeof handOver>[0]
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...userKeys.all, "handover"],
    mutationFn: handOver,
    meta: { dataId: "ADMN-006" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
      void queryClient.invalidateQueries({ queryKey: leadKeys.all });
    },
  });
}

/** ADMN-006 · Delete a person (soft: the row stays for the audit trail). */
export function useDeleteUser(): UseMutationResult<
  undefined,
  Error,
  Parameters<typeof deleteUser>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...userKeys.all, "delete"],
    mutationFn: deleteUser,
    meta: { dataId: "ADMN-006" },
    onSuccess: refresh,
  });
}
