"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { leadKeys } from "@/features/leads/api/leads.queries";

import {
  cancelApplication,
  createApplication,
  recordStage,
  uploadApplicationDocument,
  type WriteInput,
} from "./subsidy-applications.api";
import { applicationKeys } from "./subsidy-applications.queries";
import type {
  Application,
  CancelApplicationRequest,
  CreateApplicationRequest,
  RecordStageRequest,
} from "./subsidy-applications.schemas";

/** Puts the answer in the cache, and refreshes the lists, the history and the lead. */
function useSettle(): (application: Application) => void {
  const queryClient = useQueryClient();
  return (application) => {
    queryClient.setQueryData(applicationKeys.detail(application.id), application);
    void queryClient.invalidateQueries({ queryKey: applicationKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: applicationKeys.stages(application.id) });
    void queryClient.invalidateQueries({ queryKey: leadKeys.detail(application.lead.id) });
    void queryClient.invalidateQueries({ queryKey: leadKeys.timeline(application.lead.id) });
  };
}

/** SUBS-004 · Forward a lead into an application; the lead moves to won. */
export function useCreateApplication(): UseMutationResult<
  Application,
  Error,
  WriteInput<CreateApplicationRequest>
> {
  const settle = useSettle();
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...applicationKeys.all, "create"],
    mutationFn: createApplication,
    meta: { dataId: "SUBS-004" },
    onSuccess: (application) => {
      settle(application);
      void queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}

/** SUBS-006 · Record a stage, forwards or back. */
export function useRecordStage(): UseMutationResult<
  Application,
  Error,
  { applicationId: string } & WriteInput<RecordStageRequest>
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...applicationKeys.all, "stage"],
    mutationFn: ({ applicationId, ...input }) => recordStage(applicationId, input),
    meta: { dataId: "SUBS-006" },
    onSuccess: settle,
  });
}

/** SUBS-006 · Cancel, with a reason. */
export function useCancelApplication(): UseMutationResult<
  Application,
  Error,
  { applicationId: string } & WriteInput<CancelApplicationRequest>
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...applicationKeys.all, "cancel"],
    mutationFn: ({ applicationId, ...input }) => cancelApplication(applicationId, input),
    meta: { dataId: "SUBS-006" },
    onSuccess: settle,
  });
}

/** SUBS-007 · One file against a checklist item; the checklist and the count refresh. */
export function useUploadApplicationDocument(): UseMutationResult<
  void,
  Error,
  Parameters<typeof uploadApplicationDocument>[0]
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...applicationKeys.all, "upload"],
    mutationFn: uploadApplicationDocument,
    meta: { dataId: "SUBS-007" },
    onSuccess: (_result, { applicationId }) => {
      void queryClient.invalidateQueries({ queryKey: applicationKeys.checklist(applicationId) });
      void queryClient.invalidateQueries({ queryKey: applicationKeys.detail(applicationId) });
    },
  });
}
