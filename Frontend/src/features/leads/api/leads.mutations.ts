"use client";

import {
  useMutation,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import {
  addLeadNote,
  assignLead,
  createLead,
  reopenLead,
  transitionLead,
  type AddLeadNoteInput,
  type AssignLeadInput,
  type CreateLeadInput,
  type ReopenLeadInput,
  type TransitionLeadInput,
} from "./leads.api";
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

/**
 * After a stage change or an assignment: the lead on screen takes the backend's answer, and
 * its timeline, every list and the counts refetch in the background.
 */
function applyLeadChange(queryClient: QueryClient, lead: Lead): void {
  queryClient.setQueryData(leadKeys.detail(lead.id), lead);
  void queryClient.invalidateQueries({ queryKey: leadKeys.timeline(lead.id) });
  void queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
  void queryClient.invalidateQueries({ queryKey: leadKeys.stats() });
}

/** LEAD-007 · Contact, qualify, win or lose a lead. */
export function useTransitionLead(): UseMutationResult<Lead, Error, TransitionLeadInput> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...leadKeys.all, "transition"],
    mutationFn: transitionLead,
    meta: { dataId: "LEAD-007" },
    onSuccess: (lead) => {
      applyLeadChange(queryClient, lead);
    },
    onError: (_error, { leadId }) => {
      // A refusal usually means the lead moved on elsewhere: show the latest.
      void queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
    },
  });
}

/** LEAD-007 · Bring a lost lead back. */
export function useReopenLead(): UseMutationResult<Lead, Error, ReopenLeadInput> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...leadKeys.all, "reopen"],
    mutationFn: reopenLead,
    meta: { dataId: "LEAD-007" },
    onSuccess: (lead) => {
      applyLeadChange(queryClient, lead);
    },
    onError: (_error, { leadId }) => {
      void queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
    },
  });
}

/** LEAD-008 · Give the lead an owner or a channel partner, or clear either. */
export function useAssignLead(): UseMutationResult<Lead, Error, AssignLeadInput> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...leadKeys.all, "assign"],
    mutationFn: assignLead,
    meta: { dataId: "LEAD-008" },
    onSuccess: (lead) => {
      applyLeadChange(queryClient, lead);
    },
    onError: (_error, { leadId }) => {
      void queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
    },
  });
}
