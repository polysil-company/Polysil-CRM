"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { withConversationRead, withLastMessage } from "@/features/messages/lib/conversation-cache";

import { markConversationRead, sendMessage, startConversation } from "./messages.api";
import {
  conversationListQueryOptions,
  conversationMessagesQueryOptions,
  messageKeys,
  startedConversationQueryOptions,
} from "./messages.queries";
import type {
  Conversation,
  MarkConversationReadResult,
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
      queryClient.setQueryData(
        startedConversationQueryOptions(conversation.id).queryKey,
        conversation,
      );
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
