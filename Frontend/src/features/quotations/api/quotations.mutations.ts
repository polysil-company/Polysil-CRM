"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { leadKeys } from "@/features/leads/api/leads.queries";

import {
  createQuotation,
  patchQuotation,
  replaceQuotationLines,
  type SaveInput,
} from "./quotations.api";
import { quotationKeys } from "./quotations.queries";
import type {
  CreateQuotationRequest,
  PatchQuotationRequest,
  Quotation,
  ReplaceLinesRequest,
} from "./quotations.schemas";

/** A saved draft: it takes the backend's answer, and every list — a lead's too — refetches. */
function useApplySaved(): (quotation: Quotation) => void {
  const queryClient = useQueryClient();
  return (quotation) => {
    queryClient.setQueryData(quotationKeys.detail(quotation.id), quotation);
    void queryClient.invalidateQueries({ queryKey: quotationKeys.lists() });
    if (quotation.lead !== null) {
      // The lead's history gains a quotation event.
      void queryClient.invalidateQueries({ queryKey: leadKeys.timeline(quotation.lead.id) });
    }
  };
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
  readonly lines: SaveInput<ReplaceLinesRequest>;
}

/**
 * QUOT-004 · Save an existing draft: the header first when it changed (it re-prices), then the
 * whole basket. The lines' answer is the document as saved.
 */
export function useUpdateDraft(): UseMutationResult<Quotation, Error, UpdateDraftInput> {
  const applySaved = useApplySaved();
  return useMutation({
    mutationKey: [...quotationKeys.all, "update"],
    mutationFn: async ({ quotationId, header, lines }) => {
      if (header !== null) {
        await patchQuotation(quotationId, header);
      }
      return replaceQuotationLines(quotationId, lines);
    },
    meta: { dataId: "QUOT-004" },
    onSuccess: applySaved,
  });
}
