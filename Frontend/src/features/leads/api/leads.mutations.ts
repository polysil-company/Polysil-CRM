"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { addLeadNote, createLead, type AddLeadNoteInput, type CreateLeadInput } from "./leads.api";
import { leadKeys, leadTimelineQueryOptions } from "./leads.queries";
import type { Lead, TimelineEvent } from "./leads.schemas";

/**
 * LEAD-002. On success the new lead is cached for its detail page, and every lead list and
 * the count refetch in the background (not awaited, so the button shows success at once).
 */
export function useCreateLead(): UseMutationResult<Lead, Error, CreateLeadInput> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...leadKeys.all, "create"],
    mutationFn: createLead,
    meta: { dataId: "LEAD-002" },
    onSuccess: (lead) => {
      queryClient.setQueryData(leadKeys.detail(lead.id), lead);
      void queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: leadKeys.stats() });
    },
  });
}

/**
 * LEAD-006. A note is a timeline entry and moves the lead's last activity and score, so the
 * timeline, the lead and the lists refetch in the background once it is saved.
 */
export function useAddLeadNote(): UseMutationResult<TimelineEvent, Error, AddLeadNoteInput> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...leadKeys.all, "note"],
    mutationFn: addLeadNote,
    meta: { dataId: "LEAD-006" },
    onSuccess: (event, { leadId }) => {
      // Shown at once at the top of the timeline; the refetch below confirms it.
      queryClient.setQueryData(leadTimelineQueryOptions(leadId).queryKey, (data) => {
        const [newest, ...older] = data?.pages ?? [];
        if (data === undefined || newest === undefined) {
          return data;
        }
        if (newest.items.some((item) => item.id === event.id)) {
          return data;
        }
        return { ...data, pages: [{ ...newest, items: [event, ...newest.items] }, ...older] };
      });
      // The detail key is a prefix of the timeline's, so this refreshes both.
      void queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      void queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}
