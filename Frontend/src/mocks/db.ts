import type { LeadWire, TimelineEventWire } from "@/features/leads/api/leads.schemas";
import type { ConversationWire, MessageWire } from "@/features/messages/api/messages.schemas";
import type { NotificationWire } from "@/features/notifications/api/notifications.schemas";

import { generateLeads } from "./data/leads";
import { generateConversations } from "./data/messages";
import { generateNotifications } from "./data/notifications";

export interface MockDb {
  /** Newest first, in the backend's wire format. */
  leads: LeadWire[];
  notifications: NotificationWire[];
  conversations: ConversationWire[];
  messages: MessageWire[];
  /** POST /leads replays: Idempotency-Key → the request body and the lead it created. */
  leadCreations: Map<string, { body: string; leadId: string }>;
  /** Notes added through POST /leads/{id}/notes, by lead; merged into the derived timeline. */
  leadNotes: Map<string, TimelineEventWire[]>;
  /** POST /leads/{id}/notes replays: Idempotency-Key → the request body and the event. */
  noteCreations: Map<string, { body: string; event: TimelineEventWire }>;
}

function createMockDb(): MockDb {
  const leads = generateLeads();
  const { conversations, messages } = generateConversations(leads);
  return {
    leads,
    notifications: generateNotifications(leads),
    conversations,
    messages,
    leadCreations: new Map(),
    leadNotes: new Map(),
    noteCreations: new Map(),
  };
}

/** In-memory state of the mock backend. Everything created lives until the page reloads. */
export const mockDb: MockDb = createMockDb();

export function resetMockDb(): void {
  Object.assign(mockDb, createMockDb());
}
