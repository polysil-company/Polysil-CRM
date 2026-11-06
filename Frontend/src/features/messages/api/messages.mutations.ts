"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { withConversationRead, withLastMessage } from "@/features/messages/lib/conversation-cache";

import {
  addMembers,
  createGroup,
  markConversationRead,
  removeMember,
  renameGroup,
  sendMessage,
  startConversation,
} from "./messages.api";
import {
  conversationListQueryOptions,
  conversationMessagesQueryOptions,
  conversationQueryOptions,
  groupMembersQueryOptions,
  messageKeys,
} from "./messages.queries";
import type {
  Conversation,
  CreateGroupRequest,
  MarkConversationReadResult,
  Member,
  Message,
  SendMessageRequest,
} from "./messages.schemas";

/** MSG-003. The sent message joins the open thread and the conversation list at once. */
export function useSendMessage(
  conversationId: string,
): UseMutationResult<Message, Error, SendMessageRequest> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...messageKeys.all, "send", conversationId],
    mutationFn: (request: SendMessageRequest) => sendMessage(conversationId, request),
    meta: { dataId: "MSG-003" },
    onSuccess: (message) => {
      queryClient.setQueryData(conversationMessagesQueryOptions(conversationId).queryKey, (page) =>
        page === undefined || page.items.some((item) => item.id === message.id)
          ? page
          : { ...page, items: [...page.items, message] },
      );
      const listKey = conversationListQueryOptions().queryKey;
      const list = queryClient.getQueryData(listKey);
      if (list?.items.some((item) => item.id === conversationId) === true) {
        queryClient.setQueryData(listKey, withLastMessage(list, message));
      } else {
        // The first message lists a new conversation (backend/docs/api/messages.md).
        void queryClient.invalidateQueries({ queryKey: listKey });
      }
    },
  });
}

/** MSG-004. Resolves to the new — or already existing — conversation. */
export function useStartConversation(): UseMutationResult<Conversation, Error, string> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...messageKeys.all, "start"],
    mutationFn: (participantId: string) => startConversation(participantId),
    meta: { dataId: "MSG-004" },
    onSuccess: (conversation) => {
      queryClient.setQueryData(conversationQueryOptions(conversation.id).queryKey, conversation);
      void queryClient.invalidateQueries({ queryKey: messageKeys.conversations() });
    },
  });
}

/** What MSG-005 marks: the conversation, up to the newest message on screen (or null). */
export interface MarkConversationReadVariables {
  readonly conversationId: string;
  readonly upTo: string | null;
}

/** MSG-005. Clears the conversation's unread badge and updates the total in the sidebar. */
export function useMarkConversationRead(): UseMutationResult<
  MarkConversationReadResult,
  Error,
  MarkConversationReadVariables
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...messageKeys.all, "read"],
    mutationFn: ({ conversationId, upTo }: MarkConversationReadVariables) =>
      markConversationRead(conversationId, upTo),
    meta: { dataId: "MSG-005" },
    onSuccess: (result, { conversationId }) => {
      queryClient.setQueryData(conversationListQueryOptions().queryKey, (list) =>
        list === undefined ? list : withConversationRead(list, conversationId, result.unreadTotal),
      );
    },
  });
}

/** MSG-006. A new group is listed at once, before anyone writes in it. */
export function useCreateGroup(): UseMutationResult<Conversation, Error, CreateGroupRequest> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...messageKeys.all, "group", "create"],
    mutationFn: createGroup,
    meta: { dataId: "MSG-006" },
    onSuccess: (conversation) => {
      queryClient.setQueryData(conversationQueryOptions(conversation.id).queryKey, conversation);
      void queryClient.invalidateQueries({ queryKey: messageKeys.conversations() });
    },
  });
}

/** MSG-006. The manager renames the group; the list and the header follow. */
export function useRenameGroup(
  conversationId: string,
): UseMutationResult<Conversation, Error, string> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...messageKeys.all, "group", "rename", conversationId],
    mutationFn: (name: string) => renameGroup(conversationId, { name }),
    meta: { dataId: "MSG-006" },
    onSuccess: (conversation) => {
      queryClient.setQueryData(conversationQueryOptions(conversationId).queryKey, conversation);
      void queryClient.invalidateQueries({ queryKey: messageKeys.conversations() });
    },
  });
}

/** MSG-006. Any member adds colleagues; the answer is the new member list. */
export function useAddMembers(
  conversationId: string,
): UseMutationResult<readonly Member[], Error, readonly string[]> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...messageKeys.all, "group", "add", conversationId],
    mutationFn: (userIds: readonly string[]) =>
      addMembers(conversationId, { user_ids: [...userIds] }),
    meta: { dataId: "MSG-006" },
    onSuccess: (members) => {
      queryClient.setQueryData(groupMembersQueryOptions(conversationId).queryKey, members);
      void queryClient.invalidateQueries({ queryKey: messageKeys.conversations() });
    },
  });
}

/**
 * MSG-006. Leave the group (the user's own id), or, as its manager, remove someone. Leaving
 * drops the group from the user's screens: the caller moves away from it.
 */
export function useRemoveMember(
  conversationId: string,
): UseMutationResult<undefined, Error, string> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: [...messageKeys.all, "group", "remove", conversationId],
    mutationFn: (userId: string) => removeMember(conversationId, userId),
    meta: { dataId: "MSG-006" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: messageKeys.conversations() });
    },
  });
}
