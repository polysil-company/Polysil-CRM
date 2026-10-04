"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { approvalKeys } from "@/features/approvals/api/approvals.queries";
import { orderKeys } from "@/features/orders/api/orders.queries";

import {
  cancelComplaint,
  chooseRemedy,
  createSlaPolicy,
  deleteAttachment,
  uploadAttachment,
  withdrawRemedy,
  checkComplaint,
  createComplaint,
  deleteComplaint,
  patchComplaint,
  qcComplaint,
  replaceComplaintLines,
  submitComplaint,
  type WriteInput,
} from "./complaints.api";
import { complaintKeys } from "./complaints.queries";
import type {
  CancelComplaintRequest,
  CreateSlaPolicyRequest,
  RemedyRequest,
  SlaPolicy,
  WithdrawRemedyRequest,
  CheckRequest,
  Complaint,
  CreateComplaintRequest,
  PatchComplaintRequest,
  QcRequest,
  ReplaceLinesRequest,
} from "./complaints.schemas";

/** Puts the answer in the cache, and refreshes every list, count and history. */
function useSettle(): (complaint: Complaint) => void {
  const queryClient = useQueryClient();
  return (complaint) => {
    queryClient.setQueryData(complaintKeys.detail(complaint.id), complaint);
    void queryClient.invalidateQueries({ queryKey: complaintKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: complaintKeys.stats() });
    void queryClient.invalidateQueries({ queryKey: complaintKeys.timeline(complaint.id) });
  };
}

type Keyed<T> = { complaintId: string } & WriteInput<T>;

/** CMPL-003 · Save a new draft. */
export function useCreateComplaint(): UseMutationResult<
  Complaint,
  Error,
  WriteInput<CreateComplaintRequest>
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...complaintKeys.all, "create"],
    mutationFn: createComplaint,
    meta: { dataId: "CMPL-003" },
    onSuccess: settle,
  });
}

/**
 * CMPL-003 · Save a draft's changes: the header (when it changed), then the products (when
 * they changed). Two calls, each with its own key, so a retry replays only what is left.
 */
export function useSaveComplaintDraft(): UseMutationResult<
  Complaint,
  Error,
  {
    complaintId: string;
    header: WriteInput<PatchComplaintRequest> | null;
    lines: WriteInput<ReplaceLinesRequest> | null;
  }
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...complaintKeys.all, "save-draft"],
    mutationFn: async ({ complaintId, header, lines }) => {
      let saved: Complaint | null = null;
      if (header !== null) saved = await patchComplaint(complaintId, header);
      if (lines !== null) saved = await replaceComplaintLines(complaintId, lines);
      if (saved === null) {
        // The form only saves when something changed; reaching here is a programming error.
        throw new Error("Nothing to save: neither the header nor the products changed");
      }
      return saved;
    },
    meta: { dataId: "CMPL-003" },
    onSuccess: settle,
  });
}

/** CMPL-003 · Submit a draft. */
export function useSubmitComplaint(): UseMutationResult<
  Complaint,
  Error,
  { complaintId: string; idempotencyKey: string }
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...complaintKeys.all, "submit"],
    mutationFn: ({ complaintId, idempotencyKey }) => submitComplaint(complaintId, idempotencyKey),
    meta: { dataId: "CMPL-003" },
    onSuccess: settle,
  });
}

/** CMPL-003 · Cancel with a reason. */
export function useCancelComplaint(): UseMutationResult<
  Complaint,
  Error,
  Keyed<CancelComplaintRequest>
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...complaintKeys.all, "cancel"],
    mutationFn: ({ complaintId, ...input }) => cancelComplaint(complaintId, input),
    meta: { dataId: "CMPL-003" },
    onSuccess: settle,
  });
}

/** CMPL-003 · Delete a draft never submitted. */
export function useDeleteComplaint(): UseMutationResult<
  void,
  Error,
  { complaintId: string; idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...complaintKeys.all, "delete"],
    mutationFn: ({ complaintId, idempotencyKey }) => deleteComplaint(complaintId, idempotencyKey),
    meta: { dataId: "CMPL-003" },
    onSuccess: (_result, { complaintId }) => {
      queryClient.removeQueries({ queryKey: complaintKeys.detail(complaintId) });
      void queryClient.invalidateQueries({ queryKey: complaintKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: complaintKeys.stats() });
    },
  });
}

/** CMPL-004 · The manager's check. */
export function useCheckComplaint(): UseMutationResult<Complaint, Error, Keyed<CheckRequest>> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...complaintKeys.all, "check"],
    mutationFn: ({ complaintId, ...input }) => checkComplaint(complaintId, input),
    meta: { dataId: "CMPL-004" },
    onSuccess: settle,
  });
}

/** CMPL-005 · The QC verdict. */
export function useQcComplaint(): UseMutationResult<Complaint, Error, Keyed<QcRequest>> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...complaintKeys.all, "qc"],
    mutationFn: ({ complaintId, ...input }) => qcComplaint(complaintId, input),
    meta: { dataId: "CMPL-005" },
    onSuccess: settle,
  });
}

/** CMPL-007 · Choose a remedy: a refund goes into the Approvals inbox. */
export function useChooseRemedy(): UseMutationResult<Complaint, Error, Keyed<RemedyRequest>> {
  const settle = useSettle();
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...complaintKeys.all, "remedy"],
    mutationFn: ({ complaintId, ...input }) => chooseRemedy(complaintId, input),
    meta: { dataId: "CMPL-007" },
    onSuccess: (complaint) => {
      settle(complaint);
      void queryClient.invalidateQueries({ queryKey: approvalKeys.all });
      void queryClient.invalidateQueries({ queryKey: orderKeys.all });
    },
  });
}

/** CMPL-007 · Withdraw the remedy while it is still open. */
export function useWithdrawRemedy(): UseMutationResult<
  Complaint,
  Error,
  Keyed<WithdrawRemedyRequest>
> {
  const settle = useSettle();
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...complaintKeys.all, "withdraw"],
    mutationFn: ({ complaintId, ...input }) => withdrawRemedy(complaintId, input),
    meta: { dataId: "CMPL-007" },
    onSuccess: (complaint) => {
      settle(complaint);
      void queryClient.invalidateQueries({ queryKey: approvalKeys.all });
      void queryClient.invalidateQueries({ queryKey: orderKeys.all });
    },
  });
}

/** CMPL-006 · Add a file, then re-read the complaint for its list of files. */
export function useUploadAttachment(): UseMutationResult<
  void,
  Error,
  Parameters<typeof uploadAttachment>[0]
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...complaintKeys.all, "upload"],
    mutationFn: uploadAttachment,
    meta: { dataId: "CMPL-006" },
    onSuccess: (_result, { complaintId }) => {
      void queryClient.invalidateQueries({ queryKey: complaintKeys.detail(complaintId) });
      void queryClient.invalidateQueries({ queryKey: complaintKeys.timeline(complaintId) });
    },
  });
}

/** CMPL-006 · Remove a file. */
export function useDeleteAttachment(): UseMutationResult<
  void,
  Error,
  { complaintId: string; attachmentId: string; idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...complaintKeys.all, "delete-attachment"],
    mutationFn: ({ complaintId, attachmentId, idempotencyKey }) =>
      deleteAttachment(complaintId, attachmentId, idempotencyKey),
    meta: { dataId: "CMPL-006" },
    onSuccess: (_result, { complaintId }) => {
      void queryClient.invalidateQueries({ queryKey: complaintKeys.detail(complaintId) });
    },
  });
}

/** CMPL-008 · Set a new target from a day; the answer is every target. */
export function useCreateSlaPolicy(): UseMutationResult<
  SlaPolicy[],
  Error,
  WriteInput<CreateSlaPolicyRequest>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...complaintKeys.slaPolicies(), "create"],
    mutationFn: createSlaPolicy,
    meta: { dataId: "CMPL-008" },
    onSuccess: (policies) => {
      queryClient.setQueryData(complaintKeys.slaPolicies(), policies);
    },
  });
}
