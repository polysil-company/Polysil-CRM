import type { ConversationList, Message } from "@/features/messages/api/messages.schemas";

/** The list after `message` was sent: it becomes the last message and its conversation moves up. */
export function withLastMessage(list: ConversationList, message: Message): ConversationList {
  const items = list.items.map((conversation) =>
    conversation.id === message.conversationId
      ? { ...conversation, lastMessage: message, updatedAt: message.createdAt }
      : conversation,
  );
  return {
    ...list,
    items: [...items].sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt)),
  };
}

/** The list after a conversation was read, with the server's new unread total. */
export function withConversationRead(
  list: ConversationList,
  conversationId: string,
  unreadTotal: number,
): ConversationList {
  return {
    items: list.items.map((conversation) =>
      conversation.id === conversationId ? { ...conversation, unreadCount: 0 } : conversation,
    ),
    unreadTotal,
  };
}
