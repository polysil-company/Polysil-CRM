"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { leadKeys } from "@/features/leads/api/leads.queries";

import {
  createQuotation,
  deleteQuotation,
  patchQuotation,
  replaceQuotationLines,
  requestQuotationApproval,
  reviseQuotation,
  sendQuotation,
  setQuotationSubsidy,
  transitionQuotation,
  type SaveInput,
} from "./quotations.api";
import { quotationKeys } from "./quotations.queries";
import type {
  CreateQuotationRequest,
  DeleteQuotationRequest,
  PatchQuotationRequest,
  Quotation,
  QuotationSubsidyRequest,
  ReplaceLinesRequest,
  RequestApprovalRequest,
  ReviseQuotationRequest,
  SendQuotationRequest,
  TransitionQuotationRequest,
} from "./quotations.schemas";

/**
 * A quotation the backend just wrote: its document is the answer, and everything that shows
 * it refetches — the lists (a lead's too), its versions and history, and the lead, whose
 * stage a send or an answer may have moved.
 */
function useApplySaved(): (quotation: Quotation) => void {
  const queryClient = useQueryClient();
  return (quotation) => {
    queryClient.setQueryData(quotationKeys.detail(quotation.id), quotation);
    void queryClient.invalidateQueries({ queryKey: quotationKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: quotationKeys.versionLists() });
    void queryClient.invalidateQueries({ queryKey: quotationKeys.timelines() });
    if (quotation.supersedes !== null) {
      // Sending a revision marks the version it replaces.
      void queryClient.invalidateQueries({
        queryKey: quotationKeys.detail(quotation.supersedes.id),
      });
    }
    if (quotation.lead !== null) {
      void queryClient.invalidateQueries({ queryKey: leadKeys.detail(quotation.lead.id) });
      void queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    }
  };
}

/** An action on one quotation, with its body and the key that makes a retry safe. */
export interface QuotationActionInput<TBody> {
  readonly quotationId: string;
  readonly input: SaveInput<TBody>;
}

/** QUOT-004 · Create a draft on a lead. */
export function useCreateQuotation(): UseMutationResult<
  Quotation,
  Error,
  SaveInput<CreateQuotationRequest>
> {
  const applySaved = useApplySaved();
  return useMutation({
    mutationKey: [...quotationKeys.all, "create"],
    mutationFn: createQuotation,
    meta: { dataId: "QUOT-004" },
    onSuccess: applySaved,
  });
}

export interface UpdateDraftInput {
  readonly quotationId: string;
  /** Sent only when the header changed. */
  readonly header: SaveInput<PatchQuotationRequest> | null;
  /** Sent unless only the header changed (APP-009, I-05); one of the two is always sent. */
  readonly lines: SaveInput<ReplaceLinesRequest> | null;
}

/**
 * QUOT-004 · Save an existing draft: the header first when it changed (it re-prices), then the
 * whole basket unless only the header changed. The last answer is the document as saved.
 */
export function useUpdateDraft(): UseMutationResult<Quotation, Error, UpdateDraftInput> {
  const applySaved = useApplySaved();
  return useMutation({
    mutationKey: [...quotationKeys.all, "update"],
    mutationFn: async ({ quotationId, header, lines }) => {
      const patched = header === null ? null : await patchQuotation(quotationId, header);
      if (lines !== null) return replaceQuotationLines(quotationId, lines);
      if (patched === null) throw new Error("A draft save sends the header, the lines or both.");
      return patched;
    },
    meta: { dataId: "QUOT-004" },
    onSuccess: applySaved,
  });
}

/** QUOT-006 · Send a draft. */
export function useSendQuotation(): UseMutationResult<
  Quotation,
  Error,
  QuotationActionInput<SendQuotationRequest>
> {
  const applySaved = useApplySaved();
  return useMutation({
    mutationKey: [...quotationKeys.all, "send"],
    mutationFn: ({ quotationId, input }) => sendQuotation(quotationId, input),
    meta: { dataId: "QUOT-006" },
    onSuccess: applySaved,
  });
}

/** QUOT-014 · Calculate and store a subsidised draft's subsidy; the stored calculation is read again. */
export function useSetQuotationSubsidy(): UseMutationResult<
  Quotation,
  Error,
  QuotationActionInput<QuotationSubsidyRequest>
> {
  const applySaved = useApplySaved();
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...quotationKeys.all, "subsidy"],
    mutationFn: ({ quotationId, input }) => setQuotationSubsidy(quotationId, input),
    meta: { dataId: "QUOT-014" },
    onSuccess: (quotation) => {
      applySaved(quotation);
      void queryClient.invalidateQueries({
        queryKey: quotationKeys.subsidyCalculation(quotation.id),
      });
    },
  });
}

/** QUOT-007 · Ask for the discount to be approved. */
export function useRequestQuotationApproval(): UseMutationResult<
  Quotation,
  Error,
  QuotationActionInput<RequestApprovalRequest>
> {
  const applySaved = useApplySaved();
  return useMutation({
    mutationKey: [...quotationKeys.all, "request-approval"],
    mutationFn: ({ quotationId, input }) => requestQuotationApproval(quotationId, input),
    meta: { dataId: "QUOT-007" },
    onSuccess: applySaved,
  });
}

/** QUOT-008 · Record the customer's answer. */
export function useTransitionQuotation(): UseMutationResult<
  Quotation,
  Error,
  QuotationActionInput<TransitionQuotationRequest>
> {
  const applySaved = useApplySaved();
  return useMutation({
    mutationKey: [...quotationKeys.all, "transition"],
    mutationFn: ({ quotationId, input }) => transitionQuotation(quotationId, input),
    meta: { dataId: "QUOT-008" },
    onSuccess: applySaved,
  });
}

/** QUOT-009 · Revise into a new draft; the answer is the new version. */
export function useReviseQuotation(): UseMutationResult<
  Quotation,
  Error,
  QuotationActionInput<ReviseQuotationRequest>
> {
  const applySaved = useApplySaved();
  return useMutation({
    mutationKey: [...quotationKeys.all, "revise"],
    mutationFn: ({ quotationId, input }) => reviseQuotation(quotationId, input),
    meta: { dataId: "QUOT-009" },
    onSuccess: applySaved,
  });
}

/**
 * QUOT-011 · Delete a draft. The page leaves the draft on success, so only what lists it
 * refetches; its own cache entry expires unobserved.
 */
export function useDeleteQuotation(
  leadId: string | null,
): UseMutationResult<void, Error, QuotationActionInput<DeleteQuotationRequest>> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...quotationKeys.all, "delete"],
    mutationFn: ({ quotationId, input }) => deleteQuotation(quotationId, input),
    meta: { dataId: "QUOT-011" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: quotationKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: quotationKeys.versionLists() });
      if (leadId !== null) {
        void queryClient.invalidateQueries({ queryKey: leadKeys.timeline(leadId) });
      }
    },
  });
}
