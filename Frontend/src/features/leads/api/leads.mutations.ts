"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createLead } from "./leads.api";
import { leadKeys } from "./leads.queries";
import type { CreateLeadRequest, Lead } from "./leads.schemas";

/**
 * LEAD-002. On success the new lead is cached for its detail page and every
 * lead list and count refetches in the background (not awaited, so the
 * button shows success immediately).
 */
export function useCreateLead(): UseMutationResult<Lead, Error, CreateLeadRequest> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...leadKeys.all, "create"],
    mutationFn: createLead,
    meta: { dataId: "LEAD-002" },
    onSuccess: (lead) => {
      queryClient.setQueryData(leadKeys.detail(lead.id), lead);
      void queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: leadKeys.summary() });
    },
  });
}
