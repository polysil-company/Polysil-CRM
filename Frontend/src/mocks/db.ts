import type { ThresholdWire } from "@/features/approvals/api/approvals.schemas";
import type { LeadStage, LeadWire, TimelineEventWire } from "@/features/leads/api/leads.schemas";
import type { ConversationWire, MessageWire } from "@/features/messages/api/messages.schemas";
import type { NotificationWire } from "@/features/notifications/api/notifications.schemas";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";

import { seedApprovals, seedThresholds, type MockApprovalStep } from "./data/approvals";
import { generateLeads } from "./data/leads";
import { generateConversations } from "./data/messages";
import { generateNotifications } from "./data/notifications";
import { generateOrders } from "./data/orders";
import { generateQuotations } from "./data/quotations";
import { generateTasks, type MockTask } from "./data/tasks";

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
  /** Sales orders, newest first, full documents (SO-001 … SO-004, DISP-002). */
  orders: OrderWire[];
  /** Order writes: Idempotency-Key → the request and the order it made or changed. */
  orderWrites: Map<string, { body: string; orderId: string }>;
  /** Each order's history, newest first: derived once from the seed, then written to. */
  orderEvents: Map<string, TimelineEventWire[]>;
  /** When a just-approved order's PDF is ready (epoch ms); read by the next GET. */
  orderPdfReadyAt: Map<string, number>;
  /** Approval limits: an order's value and a discount, per role and territory (APPR-002). */
  thresholds: ThresholdWire[];
  /** PUT /approvals/thresholds replays: Idempotency-Key → the request. */
  thresholdWrites: Map<string, string>;
  /** The approval queue: quotation discounts and sales orders, oldest first (APPR-001). */
  approvalSteps: MockApprovalStep[];
  /** Decision replays: Idempotency-Key → the request and the step it decided. */
  approvalDecisions: Map<string, { body: string; stepId: string }>;
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
  /** Tasks, earliest due first (TASK-001…005). */
  tasks: MockTask[];
  /** Task writes: Idempotency-Key → the request and the task it made or changed. */
  taskWrites: Map<string, { body: string; taskId: string }>;
  /** How many events the mock has written, for their ids. */
  writtenEvents: number;
}

function createMockDb(): MockDb {
  const leads = generateLeads();
  const { conversations, messages } = generateConversations(leads);
  const quotations = generateQuotations(leads);
  const district = leads.find((lead) => lead.territory.level === "district")?.territory;
  const thresholds = seedThresholds(
    district === undefined ? null : { id: district.id, name: district.name, level: district.level },
  );
  const orders = generateOrders(leads, quotations, thresholds);
  const approvalSteps = seedApprovals(quotations, orders, thresholds);
  return {
    leads,
    quotations,
    quotationWrites: new Map(),
    priceVersion: 0,
    quotationEvents: new Map(),
    pdfReadyAt: new Map(),
    orders,
    orderWrites: new Map(),
    orderEvents: new Map(),
    orderPdfReadyAt: new Map(),
    thresholds,
    thresholdWrites: new Map(),
    approvalSteps,
    approvalDecisions: new Map(),
    quotationDeletes: new Map(),
    notifications: generateNotifications(leads, {
      quotation: quotations.find(
        (quotation) => quotation.status === "draft" && quotation.approval?.status === "pending",
      ),
      order: orders.find((order) => order.status === "approved"),
    }),
    conversations,
    messages,
    leadCreations: new Map(),
    leadEvents: new Map(),
    noteCreations: new Map(),
    stageChanges: new Map(),
    lostFrom: new Map(),
    tasks: generateTasks(leads),
    taskWrites: new Map(),
    writtenEvents: 1,
  };
}

/** In-memory state of the mock backend. Everything created lives until the page reloads. */
export const mockDb: MockDb = createMockDb();

export function resetMockDb(): void {
  Object.assign(mockDb, createMockDb());
}
