import type { MovementWire, WarehouseWire } from "@/features/stock/api/stock.schemas";
import type { ThresholdWire } from "@/features/approvals/api/approvals.schemas";
import type { CommissionWire, RateWire } from "@/features/commission/api/commission.schemas";
import type { SlaPolicyWire } from "@/features/complaints/api/complaints.schemas";
import type { QrCodeWire } from "@/features/lead-capture/api/lead-capture.schemas";
import type { LeadStage, LeadWire, TimelineEventWire } from "@/features/leads/api/leads.schemas";
import type { LookupList, LookupListWire } from "@/features/lookups/api/lookups.schemas";
import type { MaterialWire } from "@/features/marketing/api/marketing.schemas";
import type { ConversationWire, MessageWire } from "@/features/messages/api/messages.schemas";
import type { NotificationWire } from "@/features/notifications/api/notifications.schemas";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { PaymentWire } from "@/features/payments/api/payments.schemas";
import type { HsnRowWire, TaxRateWire } from "@/features/products/api/products.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";
import type {
  GiftWire,
  RedemptionWire,
  RewardSettingsWire,
  RuleWire,
} from "@/features/rewards/api/rewards.schemas";
import type { EntitlementWire, SchemeWire } from "@/features/schemes/api/schemes.schemas";
import type { SettingWire } from "@/features/settings/api/settings.schemas";
import type {
  ApplicationDocumentWire,
  ApplicationWire,
  StageEntryWire,
} from "@/features/subsidy/api/subsidy-applications.schemas";
import type { CalculateResponseWire } from "@/features/subsidy/api/subsidy.schemas";
import type { OfficeWire } from "@/features/users/api/users.schemas";

import { seedApprovals, seedThresholds, type MockApprovalStep } from "./data/approvals";
import { seedCommissionRates } from "./data/commission";
import { generateComplaints, seedSlaPolicies, type MockComplaint } from "./data/complaints";
import type { MockDealerApplication } from "./data/dealer-applications";
import { seedDocuments, type MockDocument } from "./data/documents";
import type { MockImportBatch } from "./data/imports";
import { seedQrCodes } from "./data/lead-capture";
import { generateLeads } from "./data/leads";
import { seedLookups, seedScoring } from "./data/lookups";
import { seedMarketingOrders, seedMaterials, type MockMarketingOrder } from "./data/marketing";
import { generateConversations, generateGroups, type MockGroupMember } from "./data/messages";
import { generateNotifications } from "./data/notifications";
import { generateOrders } from "./data/orders";
import { seedPartners, type MockPartnerRecord } from "./data/partners";
import { seedPayments, seedSchedules, type MockInstalment } from "./data/payments";
import {
  seedHsnHistory,
  seedPriceLists,
  seedProducts,
  seedTaxRates,
  type MockPriceList,
  type MockProductRecord,
} from "./data/products";
import { generateQuotations } from "./data/quotations";
import {
  seedGifts,
  seedLedger,
  seedRedemptions,
  seedRewardRules,
  seedRewardSettings,
  type MockLedgerEntry,
} from "./data/rewards";
import { seedEntitlements, seedSchemes } from "./data/schemes";
import { seedSubsidyMasters, type MockSubsidyMasters } from "./data/subsidy-masters";
import { MOCK_DEFAULT_SCHEME, seedSubsidySchemes, type MockScheme } from "./data/subsidy-schemes";
import { seedTargets, type MockTargetEntry } from "./data/targets";
import { generateTasks, seedMinutes, type MockMinutes, type MockTask } from "./data/tasks";
import type { MockAdminTerritory } from "./data/territories";
import { seedMovements, seedWarehouses } from "./data/stock";
import { seedOffices, seedUsers, type MockUserRecord } from "./data/users";

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
  /** QUOT-014 · The subsidy calculation stored with each subsidised quotation. */
  quotationSubsidyCalculations: Map<string, CalculateResponseWire["data"]>;
  /** When a just-sent quotation's PDF is ready (epoch ms); read by the next GET. */
  pdfReadyAt: Map<string, number>;
  /** Sales orders, newest first, full documents (SO-001 … SO-004, DISP-002). */
  orders: OrderWire[];
  /** Order writes: Idempotency-Key → the request and the order it made or changed. */
  orderWrites: Map<string, { body: string; orderId: string }>;
  /** SO-008 · A subsidised order's subsidy as written: null material is the order total. */
  orderSubsidies: Map<
    string,
    { material: string | null; subsidy: string; payable: string | null; leadIds: string[] }
  >;
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
  /** Who is, or was, in each group, by conversation id (MSG-006). */
  groupMembers: Map<string, MockGroupMember[]>;
  /**
   * The admin lists as Masters edits them (MSTR-009). GET /lookups/{list} reads these; other
   * mock handlers still read the seeded rows, so a row added here shows in Masters and pickers.
   */
  lookups: Record<LookupList, LookupListWire["data"]>;
  /** The lead score's settings (MSTR-010), as `GET /lookups/scoring` lists them. */
  scoring: { key: string; value: string }[];
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
  /** Meeting minutes, newest first (TASK-007). */
  minutes: MockMinutes[];
  /** POST /minutes replays: Idempotency-Key → the request and the minutes it made. */
  minutesWrites: Map<string, { body: string; minutesId: string }>;
  /** Complaints, newest first (CMPL-001…). */
  complaints: MockComplaint[];
  /** Complaint writes: Idempotency-Key → the request and the complaint it made or changed. */
  complaintWrites: Map<string, { body: string; complaintId: string }>;
  /** Each complaint's history, newest first. */
  complaintEvents: Map<string, TimelineEventWire[]>;
  /** Uploaded files, by attachment id, served back as object URLs. */
  complaintFiles: Map<string, File>;
  /** The response and resolution targets (CMPL-008). */
  slaPolicies: SlaPolicyWire[];
  /** Lead QR codes (LEAD-013). */
  qrCodes: QrCodeWire[];
  /** Stock (MSTR-014…016): the warehouses and every movement, newest first. */
  warehouses: WarehouseWire[];
  stockMovements: MovementWire[];
  /** The enquiry page's WhatsApp codes sent, by mobile (LEAD-014). */
  enquiryCodes: Map<string, number>;
  /** Today's enquiry per mobile: a second one answers the first number (LEAD-014). */
  enquiriesToday: Map<string, string>;
  /** Subsidy applications, newest first; seeded from the leads on first use (SUBS-005). */
  subsidyApplications: ApplicationWire[] | null;
  /** CHNL-007 · Dealer applications, seeded on first use (`handlers/dealer-applications.ts`). */
  dealerApplications: MockDealerApplication[] | null;
  /** MSTR-012 · The territory tree as Masters edits it, copied from the seed on first use. */
  territories: MockAdminTerritory[] | null;
  /** ADMN-007 · Company settings, seeded on first use (`handlers/settings.ts`). */
  settings: SettingWire[] | null;
  /** Each application's stage history, oldest first (SUBS-006). */
  subsidyEntries: Map<string, StageEntryWire[]>;
  /** Each application's calculation as stored at create (SUBS-006). */
  subsidyCalculations: Map<string, CalculateResponseWire["data"]>;
  /** Each application's files, by checklist code (SUBS-007). */
  subsidyDocuments: Map<string, Map<string, ApplicationDocumentWire[]>>;
  /** Uploaded application files, by document id, served back as object URLs. */
  subsidyFiles: Map<string, File>;
  /** POST /subsidy-applications replays: Idempotency-Key → the request and the application. */
  subsidyWrites: Map<string, { body: string; applicationId: string }>;
  /**
   * Each scheme's subsidy masters and matrices, every revision kept with its window (SUBS-012,
   * SUBS-013), by scheme code.
   */
  subsidyMasters: Map<string, MockSubsidyMasters>;
  /** The subsidy schemes, one per state (SUBS-014). */
  subsidySchemes: MockScheme[];
  /** How many events the mock has written, for their ids. */
  writtenEvents: number;
  /** The catalogue (MSTR-004): the quotation mock's six priced products first. */
  products: MockProductRecord[];
  /** Each product's tariff headings over time, newest first (MSTR-005). */
  hsnHistory: Map<string, HsnRowWire[]>;
  /** GST slabs by tariff code over time (MSTR-005). */
  taxRates: TaxRateWire[];
  /** Price lists with their rates (MSTR-006). */
  priceLists: MockPriceList[];
  /** Excel imports by id, as uploaded, checked and committed (MSTR-007). */
  imports: Map<string, MockImportBatch>;
  /** Documents on leads, quotations, orders and dispatches, newest first (DOC-001…003). */
  documents: MockDocument[];
  /** Uploaded document files, by document id, served back as object URLs. */
  documentFiles: Map<string, Blob>;
  /** Staff and partner users, deleted ones kept with `deleted_at` (ADMN-001…006). */
  users: MockUserRecord[];
  /** The offices a staff member is anchored on (`GET /org-units`). */
  offices: OfficeWire[];
  /** POST /users replays: Idempotency-Key → the request and the person made. */
  userWrites: Map<string, { body: string; userId: string }>;
  /** Channel partners, newest first (CHNL-001…005). */
  partners: MockPartnerRecord[];
  /** POST /partners replays: Idempotency-Key → the request and the partner made. */
  partnerWrites: Map<string, { body: string; partnerId: string }>;
  /** Promotional schemes, newest first (SCHM-001, SCHM-002). */
  schemes: SchemeWire[];
  /** Scheme credits, newest first (SCHM-004). */
  entitlements: EntitlementWire[];
  /** Every change to a monthly target, oldest first (TGT-002). */
  targets: MockTargetEntry[];
  /** Receipts, newest first, voided ones kept (ACCT-002, ACCT-003). */
  payments: PaymentWire[];
  /** Each order's planned instalments, in due order (ACCT-004). */
  paymentSchedules: Map<string, MockInstalment[]>;
  /** Dealer commissions, newest first; seeded on first use from the applications (SUBS-016, SUBS-017). */
  commissions: CommissionWire[] | null;
  /** Commission rates of every scheme (SUBS-018). */
  commissionRates: RateWire[];
  /** Reward points (RWD-001…003): every ledger row, newest first, with whose points it moves. */
  rewardLedger: MockLedgerEntry[];
  rewardRules: RuleWire[];
  /** Every settings row; the latest started is in force. */
  rewardSettings: RewardSettingsWire[];
  gifts: GiftWire[];
  /** Gift (and order) redemptions, newest first. */
  rewardRedemptions: RedemptionWire[];
  /** Marketing material (MKT-002…004): the catalogue and the orders, newest first. */
  materials: MaterialWire[];
  marketingOrders: MockMarketingOrder[];
}

function createMockDb(): MockDb {
  const products = seedProducts();
  const warehouses = seedWarehouses();
  const leads = generateLeads();
  const direct = generateConversations(leads);
  const groups = generateGroups();
  const quotations = generateQuotations(leads);
  const district = leads.find((lead) => lead.territory.level === "district")?.territory;
  const thresholds = seedThresholds(
    district === undefined ? null : { id: district.id, name: district.name, level: district.level },
  );
  const orders = generateOrders(leads, quotations, thresholds);
  const gifts = seedGifts();
  const materials = seedMaterials();
  const partners = seedPartners();
  const firstDealer = partners.find((partner) => partner.partner_type === "dealer");
  const approvalSteps = seedApprovals(quotations, orders, thresholds);
  const { tasks, minutes } = seedMinutes(generateTasks(leads));
  return {
    leads,
    quotations,
    quotationWrites: new Map(),
    priceVersion: 0,
    quotationEvents: new Map(),
    quotationSubsidyCalculations: new Map(),
    pdfReadyAt: new Map(),
    orders,
    orderWrites: new Map(),
    orderSubsidies: new Map(),
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
    conversations: [...direct.conversations, ...groups.conversations],
    messages: [...direct.messages, ...groups.messages],
    groupMembers: groups.members,
    lookups: seedLookups(),
    scoring: seedScoring(),
    leadCreations: new Map(),
    leadEvents: new Map(),
    noteCreations: new Map(),
    stageChanges: new Map(),
    lostFrom: new Map(),
    tasks,
    taskWrites: new Map(),
    minutes,
    minutesWrites: new Map(),
    complaints: generateComplaints(leads, orders),
    complaintWrites: new Map(),
    complaintEvents: new Map(),
    complaintFiles: new Map(),
    slaPolicies: seedSlaPolicies(),
    qrCodes: seedQrCodes(),
    warehouses,
    stockMovements: seedMovements(products, warehouses),
    enquiryCodes: new Map(),
    enquiriesToday: new Map(),
    subsidyApplications: null,
    dealerApplications: null,
    territories: null,
    settings: null,
    subsidyEntries: new Map(),
    subsidyCalculations: new Map(),
    subsidyDocuments: new Map(),
    subsidyFiles: new Map(),
    subsidyWrites: new Map(),
    subsidyMasters: new Map([[MOCK_DEFAULT_SCHEME, seedSubsidyMasters()]]),
    subsidySchemes: seedSubsidySchemes(),
    writtenEvents: 1,
    products,
    hsnHistory: seedHsnHistory(products),
    taxRates: seedTaxRates(),
    priceLists: seedPriceLists(products),
    imports: new Map(),
    documents: seedDocuments(leads, quotations, orders),
    documentFiles: new Map(),
    users: seedUsers(),
    offices: seedOffices(),
    userWrites: new Map(),
    partners,
    partnerWrites: new Map(),
    schemes: seedSchemes(products[0]?.id ?? null),
    entitlements: seedEntitlements(
      orders[0] === undefined ? null : { id: orders[0].id, order_no: orders[0].order_no },
    ),
    targets: seedTargets(),
    payments: seedPayments(orders),
    paymentSchedules: seedSchedules(orders),
    commissions: null,
    commissionRates: seedCommissionRates(),
    rewardLedger: seedLedger(
      firstDealer === undefined
        ? null
        : { type: "partner", id: firstDealer.id, name: firstDealer.name },
    ),
    rewardRules: seedRewardRules(),
    rewardSettings: seedRewardSettings(),
    gifts,
    rewardRedemptions: seedRedemptions(gifts),
    materials,
    marketingOrders: seedMarketingOrders(materials),
  };
}

/** In-memory state of the mock backend. Everything created lives until the page reloads. */
export const mockDb: MockDb = createMockDb();

export function resetMockDb(): void {
  Object.assign(mockDb, createMockDb());
}
