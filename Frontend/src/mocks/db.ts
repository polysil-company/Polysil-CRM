import type { LeadStage, LeadWire, TimelineEventWire } from "@/features/leads/api/leads.schemas";
import type { ConversationWire, MessageWire } from "@/features/messages/api/messages.schemas";
import type { NotificationWire } from "@/features/notifications/api/notifications.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";

import { generateLeads } from "./data/leads";
import { generateConversations } from "./data/messages";
import { generateNotifications } from "./data/notifications";
import { generateQuotations } from "./data/quotations";

export interface MockDb {
  /** Newest first, in the backend's wire format. */
  leads: LeadWire[];
  /** Newest first, full documents; list rows are derived from them. */
  quotations: QuotationWire[];
  /** Quotation saves: Idempotency-Key → the request and the quotation it made or changed. */
  quotationWrites: Map<string, { body: string; quotationId: string }>;
  /** Bumped to publish a new price list: saves priced before it get 409 rate_changed. */
  priceVersion: number;
  /** Each quotation's history, newest first: derived once from the seed, then written to. */
  quotationEvents: Map<string, TimelineEventWire[]>;
  /** When a just-sent quotation's PDF is ready (epoch ms); read by the next GET. */
  pdfReadyAt: Map<string, number>;
  /** When the mock's stand-in manager approves a pending discount request (epoch ms). */
  approvalDecideAt: Map<string, number>;
  /** DELETE /quotations/{id} replays: Idempotency-Key → the request. */
  quotationDeletes: Map<string, string>;
  notifications: NotificationWire[];
  conversations: ConversationWire[];
  messages: MessageWire[];
  /** POST /leads replays: Idempotency-Key → the request body and the lead it created. */
  leadCreations: Map<string, { body: string; leadId: string }>;
  /** Events written through the mock (notes, stage changes), by lead, newest first. */
  leadEvents: Map<string, TimelineEventWire[]>;
  /** POST /leads/{id}/notes replays: Idempotency-Key → the request body and the event. */
  noteCreations: Map<string, { body: string; event: TimelineEventWire }>;
  /** Stage changes and reopenings: Idempotency-Key → the request, for replay and 409. */
  stageChanges: Map<string, { body: string; leadId: string }>;
  /** The stage each lead was lost from, for reopening (the backend's `lost_from`). */
  lostFrom: Map<string, LeadStage>;
  /** How many events the mock has written, for their ids. */
  writtenEvents: number;
}

function createMockDb(): MockDb {
  const leads = generateLeads();
  const { conversations, messages } = generateConversations(leads);
  return {
    leads,
    quotations: generateQuotations(leads),
    quotationWrites: new Map(),
    priceVersion: 0,
    quotationEvents: new Map(),
    pdfReadyAt: new Map(),
    approvalDecideAt: new Map(),
    quotationDeletes: new Map(),
    notifications: generateNotifications(leads),
    conversations,
    messages,
    leadCreations: new Map(),
    leadEvents: new Map(),
    noteCreations: new Map(),
    stageChanges: new Map(),
    lostFrom: new Map(),
    writtenEvents: 1,
  };
}

/** In-memory state of the mock backend. Everything created lives until the page reloads. */
export const mockDb: MockDb = createMockDb();

export function resetMockDb(): void {
  Object.assign(mockDb, createMockDb());
}
