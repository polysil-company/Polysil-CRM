"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { lookupKeys, lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import type { LookupItem, LookupList } from "@/features/lookups/api/lookups.schemas";
import { userKeys } from "@/features/users/api/users.queries";

import {
  addLookupItem,
  createOffice,
  createTerritory,
  patchOffice,
  patchTerritory,
  patchScoring,
  setOfficeOpen,
  updateLookupItem,
} from "./masters.api";
import { masterKeys, scoringQueryOptions } from "./masters.queries";
import type {
  LookupCreateRequest,
  LookupUpdateRequest,
  Office,
  OfficeCreateRequest,
  OfficePatchRequest,
  ScoringItem,
  ScoringPatchRequest,
  Territory,
  TerritoryCreateRequest,
  TerritoryPatchRequest,
} from "./masters.schemas";

/** MSTR-009. Every picker that reads the list refreshes. */
export function useAddLookupItem(
  list: LookupList,
): UseMutationResult<LookupItem, Error, LookupCreateRequest> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["masters", "lookup", "add", list],
    mutationFn: (body: LookupCreateRequest) => addLookupItem(list, body),
    meta: { dataId: "MSTR-009" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: lookupKeys.list(list) });
    },
  });
}

export interface UpdateLookupItemVariables {
  readonly itemId: string;
  readonly body: LookupUpdateRequest;
}

/** MSTR-009. The row changes in place; pickers refresh. */
export function useUpdateLookupItem(
  list: LookupList,
): UseMutationResult<LookupItem, Error, UpdateLookupItemVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["masters", "lookup", "update", list],
    mutationFn: ({ itemId, body }: UpdateLookupItemVariables) =>
      updateLookupItem(list, itemId, body),
    meta: { dataId: "MSTR-009" },
    onSuccess: (item) => {
      queryClient.setQueryData(lookupListQueryOptions(list).queryKey, (rows) =>
        rows?.map((row) => (row.id === item.id ? item : row)),
      );
      void queryClient.invalidateQueries({ queryKey: lookupKeys.list(list) });
    },
  });
}

/** MSTR-010. The answer is every setting, as now stored. */
export function usePatchScoring(): UseMutationResult<ScoringItem[], Error, ScoringPatchRequest> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["masters", "scoring"],
    mutationFn: patchScoring,
    meta: { dataId: "MSTR-010" },
    onSuccess: (items) => {
      queryClient.setQueryData(scoringQueryOptions().queryKey, items);
    },
  });
}

/** Every office list, and the office pickers on the people forms, see the change. */
function useRefreshOffices(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: masterKeys.offices() });
    void queryClient.invalidateQueries({ queryKey: userKeys.all });
  };
}

/** MSTR-011. */
export function useCreateOffice(): UseMutationResult<Office, Error, OfficeCreateRequest> {
  const refresh = useRefreshOffices();
  return useMutation({
    mutationKey: ["masters", "office", "create"],
    mutationFn: createOffice,
    meta: { dataId: "MSTR-011" },
    onSuccess: refresh,
  });
}

export interface PatchOfficeVariables {
  readonly officeId: string;
  readonly body: OfficePatchRequest;
}

/** MSTR-011. */
export function usePatchOffice(): UseMutationResult<Office, Error, PatchOfficeVariables> {
  const refresh = useRefreshOffices();
  return useMutation({
    mutationKey: ["masters", "office", "patch"],
    mutationFn: ({ officeId, body }: PatchOfficeVariables) => patchOffice(officeId, body),
    meta: { dataId: "MSTR-011" },
    onSuccess: refresh,
  });
}

export interface SetOfficeOpenVariables {
  readonly officeId: string;
  readonly open: boolean;
}

/** MSTR-011. Close (refused while people are anchored on it) or reopen. */
export function useSetOfficeOpen(): UseMutationResult<Office, Error, SetOfficeOpenVariables> {
  const refresh = useRefreshOffices();
  return useMutation({
    mutationKey: ["masters", "office", "open"],
    mutationFn: ({ officeId, open }: SetOfficeOpenVariables) => setOfficeOpen(officeId, open),
    meta: { dataId: "MSTR-011" },
    onSuccess: refresh,
  });
}

/** Every territory list, and the territory pickers (`/lookups/territories`), see the change. */
function useRefreshTerritories(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: masterKeys.territories() });
    void queryClient.invalidateQueries({ queryKey: [...lookupKeys.all, "territories"] });
  };
}

/** MSTR-012. */
export function useCreateTerritory(): UseMutationResult<Territory, Error, TerritoryCreateRequest> {
  const refresh = useRefreshTerritories();
  return useMutation({
    mutationKey: ["masters", "territory", "create"],
    mutationFn: createTerritory,
    meta: { dataId: "MSTR-012" },
    onSuccess: refresh,
  });
}

export interface PatchTerritoryVariables {
  readonly territoryId: string;
  readonly body: TerritoryPatchRequest;
}

/** MSTR-012. */
export function usePatchTerritory(): UseMutationResult<Territory, Error, PatchTerritoryVariables> {
  const refresh = useRefreshTerritories();
  return useMutation({
    mutationKey: ["masters", "territory", "patch"],
    mutationFn: ({ territoryId, body }: PatchTerritoryVariables) =>
      patchTerritory(territoryId, body),
    meta: { dataId: "MSTR-012" },
    onSuccess: refresh,
  });
}
