import { apiRequest } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  conversationListResponseSchema,
  conversationResponseSchema,
  markConversationReadResponseSchema,
  messageListResponseSchema,
  messageResponseSchema,
  staffDirectoryResponseSchema,
  type Conversation,
  type ConversationList,
  type MarkConversationReadResult,
  type Message,
  type MessagePage,
  type Person,
  type SendMessageRequest,
  type StartConversationRequest,
} from "./messages.schemas";

const log = createLogger({ file: "features/messages/api/messages.api.ts", dataId: "MSG-001" });

/** Messages loaded per conversation. TODO(MSG-002): load older messages with `nextCursor`. */
export const MESSAGE_PAGE_SIZE = 50;

/** People shown per directory search. */
export const STAFF_DIRECTORY_LIMIT = 20;

function conversationPath(conversationId: string): ApiPath {
  return `/conversations/${encodeURIComponent(conversationId)}`;
}

/** MSG-001 · GET /conversations */
export function listConversations(signal?: AbortSignal): Promise<ConversationList> {
  return apiRequest({
    dataId: "MSG-001",
    logger: log,
    fn: "listConversations",
    path: "/conversations",
    schema: conversationListResponseSchema,
    signal,
  });
}

/** MSG-002 · GET /conversations/{conversationId}/messages */
export function listMessages(conversationId: string, signal?: AbortSignal): Promise<MessagePage> {
  return apiRequest({
    dataId: "MSG-002",
    logger: log,
    fn: "listMessages",
    path: `${conversationPath(conversationId)}/messages`,
    query: { limit: MESSAGE_PAGE_SIZE },
    schema: messageListResponseSchema,
    signal,
  });
}

/** MSG-003 · POST /conversations/{conversationId}/messages */
export function sendMessage(conversationId: string, body: SendMessageRequest): Promise<Message> {
  return apiRequest({
    dataId: "MSG-003",
    logger: log,
    fn: "sendMessage",
    method: "POST",
    path: `${conversationPath(conversationId)}/messages`,
    body,
    schema: messageResponseSchema,
  });
}

/** MSG-004 · GET /staff-directory */
export function searchStaffDirectory(q: string, signal?: AbortSignal): Promise<readonly Person[]> {
  return apiRequest({
    dataId: "MSG-004",
    logger: log,
    fn: "searchStaffDirectory",
    path: "/staff-directory",
    query: { q, limit: STAFF_DIRECTORY_LIMIT },
    schema: staffDirectoryResponseSchema,
    signal,
  });
}

/** MSG-004 · POST /conversations */
export function startConversation(participantId: string): Promise<Conversation> {
  const body: StartConversationRequest = { participant_id: participantId };
  return apiRequest({
    dataId: "MSG-004",
    logger: log,
    fn: "startConversation",
    method: "POST",
    path: "/conversations",
    body,
    schema: conversationResponseSchema,
  });
}

/** MSG-005 · POST /conversations/{conversationId}/read */
export function markConversationRead(conversationId: string): Promise<MarkConversationReadResult> {
  return apiRequest({
    dataId: "MSG-005",
    logger: log,
    fn: "markConversationRead",
    method: "POST",
    path: `${conversationPath(conversationId)}/read`,
    schema: markConversationReadResponseSchema,
  });
}
