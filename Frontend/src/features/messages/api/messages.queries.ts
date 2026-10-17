import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import {
  getConversation,
  listConversations,
  listMessages,
  searchStaffDirectory,
} from "./messages.api";

/**
 * How often new messages are checked for. Polling pauses while the tab is hidden and
 * refetches when it comes back. The open conversation checks more often, because a
 * reply that takes half a minute to appear feels broken.
 * TODO(MSG-001): replace with push once the backend chooses a transport.
 */
export const CONVERSATION_LIST_POLL_MS = 30_000;
export const OPEN_CONVERSATION_POLL_MS = 10_000;

/**
 * Query keys for messages. Invalidate by prefix:
 *   messageKeys.all             → everything about messages
 *   messageKeys.conversations() → the conversation list and unread counts, and each
 *                                 conversation read on its own
 */
export const messageKeys = {
  all: ["messages"] as const,
  conversations: () => [...messageKeys.all, "conversations"] as const,
  thread: (conversationId: string) => [...messageKeys.all, "thread", conversationId] as const,
  conversation: (conversationId: string) =>
    [...messageKeys.conversations(), conversationId] as const,
  directory: (q: string) => [...messageKeys.all, "directory", q] as const,
};

export function conversationListQueryOptions() {
  return queryOptions({
    queryKey: messageKeys.conversations(),
    queryFn: ({ signal }) => listConversations(signal),
    refetchInterval: CONVERSATION_LIST_POLL_MS,
    staleTime: 10_000,
    meta: { dataId: "MSG-001" },
  });
}

export function conversationMessagesQueryOptions(conversationId: string) {
  return queryOptions({
    queryKey: messageKeys.thread(conversationId),
    queryFn: ({ signal }) => listMessages(conversationId, signal),
    refetchInterval: OPEN_CONVERSATION_POLL_MS,
    meta: { dataId: "MSG-002" },
  });
}

/**
 * One conversation, read on its own (BE-021). The list holds a conversation only once someone
 * writes in it, so the thread reads this for one that isn't listed: just started, or opened
 * after a reload or from a link. Starting one seeds it with the backend's answer.
 */
export function conversationQueryOptions(conversationId: string) {
  return queryOptions({
    queryKey: messageKeys.conversation(conversationId),
    queryFn: ({ signal }) => getConversation(conversationId, signal),
    staleTime: 60_000,
    meta: { dataId: "MSG-004" },
  });
}

/** The directory changes rarely; keep earlier results on screen while a new search loads. */
export function staffDirectoryQueryOptions(q: string) {
  return queryOptions({
    queryKey: messageKeys.directory(q),
    queryFn: ({ signal }) => searchStaffDirectory(q, signal),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
    meta: { dataId: "MSG-004" },
  });
}
