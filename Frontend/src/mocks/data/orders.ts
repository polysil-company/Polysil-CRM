import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type {
  DispatchWire,
  OrderLineWire,
  OrderSummaryWire,
  OrderWire,
} from "@/features/orders/api/orders.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";

import { MOCK_PRODUCTS, MOCK_SELLER } from "./quotations";
import { MOCK_ID_SPACE, MOCK_STAFF, mockUuid } from "./reference";

/**
 * SO-001 … SO-004, DISP-002 · Sales orders for the mock backend, made from the seeded accepted
 * quotations as the backend makes them: the lines are imported with their figures, the
 * party is the lead's farmer, and the approval chain is chosen by value.
 */

const HOUR = 60 * 60 * 1000;
/** A seeded order's whole story — drafted to closed — fits in this, and ends before now. */
const SEED_STORY = 16 * HOUR;

// ── quantities in thousandths, as decimal strings at three places ──────────────────

export function milli(value: string): number {
  return Math.round(Number(value) * 1000);
}

export function qtyText(thousandths: number): string {
  return (thousandths / 1000).toFixed(3);
}

// ── the approval chain ───────────────────────────────────────────────────────────

/** The stand-in bands, including GST: District to 1,00,000; State to 5,00,000; Regional above. */
const DISTRICT_CEILING = 100_000;
const STATE_CEILING = 500_000;

/**
 * Every manager level up to the order's band, then Accounts, then Dispatch. The mock's owners
 * are field officers, so no level is skipped for the owner's own rank.
 */
export function chainFor(total: string): string[] {
  const amount = Number(total);
  const managers =
    amount <= DISTRICT_CEILING
      ? ["district_manager"]
      : amount <= STATE_CEILING
        ? ["district_manager", "state_manager"]
        : ["district_manager", "state_manager", "regional_manager"];
  return [...managers, "account_manager", "dispatch_manager"];
}

type ApprovalWire = NonNullable<OrderWire["approval"]>;
type StepWire = ApprovalWire["steps"][number];

/** A fresh chain's steps; `idBase` keeps each chain's step ids apart from every other's. */
export function chainSteps(roles: readonly string[], idBase: number): StepWire[] {
  return roles.map((role, index) => ({
    id: mockUuid(MOCK_ID_SPACE.approval, idBase + index),
    seq: index + 1,
    role,
    decided_role: null,
    decision: null,
    by: null,
    remark: null,
    decided_at: null,
  }));
}

/** Ids handed out so far, per space: every line and dispatch gets its own. */
const issued = { orderLine: 0, dispatch: 0 };

export function nextMockId(space: keyof typeof issued): string {
  issued[space] += 1;
  return mockUuid(MOCK_ID_SPACE[space], issued[space]);
}

// ── lines and status ──────────────────────────────────────────────────────────────

function orderLineFrom(line: QuotationWire["lines"][number]): OrderLineWire {
  const product = MOCK_PRODUCTS.find((item) => item.id === line.product_id);
  return {
    id: nextMockId("orderLine"),
    line_no: line.line_no,
    product_id: line.product_id,
    description: line.description,
    hsn_code: line.hsn_code,
    uom: line.uom,
    uom_decimals: product?.uomDecimals ?? 0,
    qty: line.qty,
    rate: line.rate,
    gross: line.gross,
    discount_pct: line.discount_pct,
    discount1_amt: line.discount1_amt,
    after_discount1: line.after_discount1,
    discount2_pct: line.discount2_pct,
    discount2_amt: line.discount2_amt,
    after_discount2: line.after_discount2,
    discount3_pct: line.discount3_pct,
    discount3_amt: line.discount3_amt,
    discount: line.discount,
    taxable: line.taxable,
    gst_slab: line.gst_slab,
    cgst_rate: line.cgst_rate,
    sgst_rate: line.sgst_rate,
    igst_rate: line.igst_rate,
    cgst: line.cgst,
    sgst: line.sgst,
    igst: line.igst,
    total: line.total,
    provisional_fields: line.provisional_fields,
    qty_dispatched: "0.000",
    qty_short: "0.000",
    qty_open: line.qty,
  };
}

/**
 * After a dispatch, a void or a close, the status is worked out from the lines: all sent is
 * dispatched, some sent is partly dispatched, nothing sent stays approved.
 */
export function statusFromLines(lines: readonly OrderLineWire[]): OrderWire["status"] {
  const open = lines.reduce((sum, line) => sum + milli(line.qty_open), 0);
  const sent = lines.reduce((sum, line) => sum + milli(line.qty_dispatched), 0);
  const short = lines.reduce((sum, line) => sum + milli(line.qty_short), 0);
  if (open === 0 && short > 0) {
    return "closed_short";
  }
  if (open === 0) {
    return "dispatched";
  }
  return sent > 0 ? "partially_dispatched" : "approved";
}

/** Share of the ordered quantity sent, 0 to 100, as the list shows it. */
export function dispatchedPct(lines: readonly OrderLineWire[]): number {
  const ordered = lines.reduce((sum, line) => sum + milli(line.qty), 0);
  const sent = lines.reduce((sum, line) => sum + milli(line.qty_dispatched), 0);
  return ordered === 0 ? 0 : Math.floor((sent / ordered) * 100);
}

export interface MockOrderInput {
  readonly id: string;
  readonly quotations: readonly QuotationWire[];
  readonly lead: LeadWire | undefined;
  readonly orderType: OrderWire["order_type"];
  readonly deliveryAddress: string | null;
  readonly paymentTerms: OrderWire["payment_terms"];
  readonly remarks: string | null;
  readonly createdAt: string;
}

/** SO-003 · A draft from accepted quotations: the lines and header come from them. */
export function mockOrderFromQuotations(input: MockOrderInput): OrderWire {
  const [first] = input.quotations;
  if (first === undefined) {
    throw new Error("An order needs at least one quotation");
  }
  const lines = input.quotations
    .flatMap((quotation) => quotation.lines)
    .map((line, index) => orderLineFrom({ ...line, line_no: index + 1 }));
  const consolidated = new Set(input.quotations.map((quotation) => quotation.lead?.id)).size > 1;
  const partyName = consolidated && first.partner?.name ? first.partner.name : first.party.name;
  return {
    doc_type: "sales_order",
    id: input.id,
    order_no: null,
    status: "draft",
    order_type: input.orderType,
    party: consolidated
      ? { name: partyName, mobile: null, address: null, gstin: null }
      : {
          name: first.party.name,
          mobile: first.party.mobile,
          address: first.party.address ?? null,
          gstin: first.party.gstin ?? null,
        },
    partner:
      first.partner === null
        ? null
        : {
            id: first.partner.id,
            name: first.partner.name ?? "",
            partner_type: first.partner.partner_type ?? null,
          },
    lead:
      consolidated || input.lead === undefined
        ? null
        : { id: input.lead.id, inquiry_no: input.lead.inquiry_no },
    quotations: input.quotations.map((quotation) => ({
      id: quotation.id,
      quote_no: quotation.quote_no,
      version: quotation.version,
    })),
    owner: first.owner,
    owner_org_unit: first.owner_org_unit,
    territory: first.territory,
    delivery_address: input.deliveryAddress,
    payment_terms: input.paymentTerms,
    seller: {
      gstin: MOCK_SELLER.gstin,
      legal_name: MOCK_SELLER.legal_name,
      address: MOCK_SELLER.address,
      state_code: MOCK_SELLER.state,
    },
    place_of_supply: first.place_of_supply.territory,
    intra_state: first.intra_state,
    price_effective_date: first.price_effective_date,
    tax_date: input.createdAt.slice(0, 10),
    is_provisional: lines.some((line) => line.provisional_fields.length > 0),
    lines,
    totals: {
      gross: sumMoney(lines, "gross"),
      discount: sumMoney(lines, "discount"),
      taxable: sumMoney(lines, "taxable"),
      cgst: sumMoney(lines, "cgst"),
      sgst: sumMoney(lines, "sgst"),
      igst: sumMoney(lines, "igst"),
      total: sumMoney(lines, "total"),
    },
    approval: null,
    last_rejection: null,
    dispatches: [],
    warnings: [],
    remarks: input.remarks,
    pdf_state: "none",
    pdf_error: null,
    confirmation: null,
    submitted_at: null,
    approved_at: null,
    cancelled_at: null,
    cancel_remark: null,
    closed_at: null,
    close_remark: null,
    created_at: input.createdAt,
  };
}

type MoneyField = "gross" | "discount" | "taxable" | "cgst" | "sgst" | "igst" | "total";

function sumMoney(lines: readonly OrderLineWire[], field: MoneyField): string {
  const paise = lines.reduce((sum, line) => sum + Math.round(Number(line[field]) * 100), 0);
  return (paise / 100).toFixed(2);
}

/** The list row: the header without lines. */
export function toOrderSummary(order: OrderWire): OrderSummaryWire {
  const waiting =
    order.status === "submitted"
      ? (order.approval?.steps.find((step) => step.decision === null)?.role ?? null)
      : null;
  return {
    id: order.id,
    order_no: order.order_no,
    status: order.status,
    order_type: order.order_type,
    party_name: order.party.name,
    partner: order.partner,
    owner: order.owner,
    totals: order.totals,
    is_provisional: order.is_provisional,
    dispatched_pct: dispatchedPct(order.lines),
    approval_waiting_on: waiting,
    submitted_at: order.submitted_at,
    created_at: order.created_at,
  };
}

export function orderNumber(serial: number): string {
  return `SO/GJ/2026-27/${String(serial).padStart(5, "0")}`;
}

/** A dispatch of every open quantity (or `share` of it), as Dispatch records it. */
export function dispatchOf(
  order: OrderWire,
  sequence: number,
  share: number,
  at: string,
): DispatchWire {
  const lines = order.lines
    .map((line) => {
      const open = milli(line.qty_open);
      const step = line.uom_decimals === 0 ? 1000 : 10 ** (3 - line.uom_decimals);
      const take = Math.max(step, Math.floor((open * share) / step) * step);
      return { order_line_id: line.id, line_no: line.line_no, qty: qtyText(Math.min(open, take)) };
    })
    .filter((line) => milli(line.qty) > 0);
  return {
    id: nextMockId("dispatch"),
    order: { id: order.id, order_no: order.order_no, party_name: order.party.name },
    dispatch_no: `D/${order.order_no ?? "draft"}/${String(sequence)}`,
    dc_no: `DC-${String(2200 + serialOf(order) * 10 + sequence)}`,
    dc_date: at.slice(0, 10),
    invoice_no: `GJ/INV/${String(900 + serialOf(order) * 10 + sequence)}`,
    invoice_date: at.slice(0, 10),
    dispatched_at: at,
    transporter: "Shree Logistics",
    vehicle_no: "GJ06AB1234",
    dispatched_by: MOCK_STAFF[4] ?? null,
    voided_at: null,
    void_remark: null,
    lines,
    warnings: [],
  };
}

/** Moves a dispatch's quantities from open to sent (or back, on a void). */
export function applyDispatch(order: OrderWire, dispatch: DispatchWire, direction: 1 | -1): void {
  order.lines = order.lines.map((line) => {
    const sent = dispatch.lines.find((item) => item.order_line_id === line.id);
    if (sent === undefined) {
      return line;
    }
    const qty = milli(sent.qty) * direction;
    return {
      ...line,
      qty_dispatched: qtyText(milli(line.qty_dispatched) + qty),
      qty_open: qtyText(milli(line.qty_open) - qty),
    };
  });
  order.status = statusFromLines(order.lines);
}

function approveEvery(steps: StepWire[], upTo: number, at: number): StepWire[] {
  return steps.map((step, index) =>
    index < upTo
      ? {
          ...step,
          decision: "approve",
          by: MOCK_STAFF[index + 1] ?? null,
          decided_at: new Date(at + (index + 1) * HOUR).toISOString(),
        }
      : step,
  );
}

type Seed =
  | "partly_dispatched"
  | "dispatched"
  | "waiting_state"
  | "waiting_district"
  | "approved"
  | "returned"
  | "cancelled"
  | "closed_short";

const SEEDS: readonly Seed[] = [
  "partly_dispatched",
  "waiting_district",
  "approved",
  "waiting_state",
  "dispatched",
  "returned",
  "cancelled",
  "closed_short",
];

/**
 * SO-001 · One order per accepted quotation, up to eight, in every state the order screens
 * show: partly and fully dispatched, waiting at District and further up the chain, approved,
 * returned to draft with the reason, cancelled and closed short.
 */
export function generateOrders(
  leads: readonly LeadWire[],
  quotations: readonly QuotationWire[],
): OrderWire[] {
  const accepted = quotations.filter(
    (quotation) => quotation.status === "accepted" && quotation.superseded_by === null,
  );
  const orders: OrderWire[] = [];
  for (const [index, quotation] of accepted.slice(0, SEEDS.length).entries()) {
    const seed = SEEDS[index];
    if (seed === undefined) {
      continue;
    }
    const acceptedMs = Date.parse(quotation.accepted_at ?? quotation.created_at);
    const createdMs = Math.min(acceptedMs + HOUR, Date.now() - SEED_STORY);
    const order = mockOrderFromQuotations({
      id: mockUuid(MOCK_ID_SPACE.order, index + 1),
      quotations: [quotation],
      lead: leads.find((lead) => lead.id === quotation.lead?.id),
      orderType: quotation.sales_type === "industrial" ? "industrial" : "commercial",
      deliveryAddress: quotation.party.address ?? null,
      paymentTerms: index % 3 === 0 ? "credit" : "full_payment",
      remarks: index % 2 === 0 ? "Deliver before the sowing season." : null,
      createdAt: new Date(createdMs).toISOString(),
    });
    orders.push(seedState(order, seed, index, createdMs));
  }
  return orders.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

function seedState(order: OrderWire, seed: Seed, index: number, createdMs: number): OrderWire {
  const submittedMs = createdMs + 2 * HOUR;
  const steps = chainSteps(chainFor(order.totals.total), 50_000 + index * 10);
  order.order_no = orderNumber(index + 1);
  order.submitted_at = new Date(submittedMs).toISOString();
  const approvedMs = submittedMs + (steps.length + 1) * HOUR;

  switch (seed) {
    case "waiting_district":
      order.status = "submitted";
      order.approval = { request_id: requestIdFor(order.id), status: "pending", steps };
      return order;
    case "waiting_state":
      order.status = "submitted";
      order.approval = {
        request_id: requestIdFor(order.id),
        status: "pending",
        steps: approveEvery(steps, 1, submittedMs),
      };
      return order;
    case "returned":
      order.status = "draft";
      order.approval = {
        request_id: requestIdFor(order.id),
        status: "rejected",
        steps: steps.map((step, stepIndex) =>
          stepIndex === 0
            ? {
                ...step,
                decision: "reject",
                by: MOCK_STAFF[1] ?? null,
                remark:
                  "Add the delivery address and confirm the lateral quantity with the farmer.",
                decided_at: new Date(submittedMs + HOUR).toISOString(),
              }
            : step,
        ),
      };
      order.last_rejection = {
        remark: "Add the delivery address and confirm the lateral quantity with the farmer.",
        role: "district_manager",
        at: new Date(submittedMs + HOUR).toISOString(),
      };
      order.delivery_address = null;
      return order;
    case "cancelled":
      order.status = "cancelled";
      order.approval = {
        request_id: requestIdFor(order.id),
        status: "cancelled",
        steps,
      };
      order.cancelled_at = new Date(submittedMs + 5 * HOUR).toISOString();
      order.cancel_remark = "The farmer bought from a local dealer instead.";
      return order;
    default:
      break;
  }

  // Approved, then dispatched as the seed says.
  order.approval = {
    request_id: requestIdFor(order.id),
    status: "approved",
    steps: approveEvery(steps, steps.length, submittedMs),
  };
  order.status = "approved";
  order.approved_at = new Date(approvedMs).toISOString();
  order.pdf_state = "ready";
  order.confirmation = order.party.mobile ? "queued" : "no_mobile";

  if (seed === "partly_dispatched" || seed === "dispatched" || seed === "closed_short") {
    const first = dispatchOf(
      order,
      1,
      seed === "dispatched" ? 1 : 0.5,
      new Date(approvedMs + 3 * HOUR).toISOString(),
    );
    order.dispatches = [first];
    applyDispatch(order, first, 1);
  }
  if (seed === "closed_short") {
    order.lines = order.lines.map((line) => ({
      ...line,
      qty_short: line.qty_open,
      qty_open: "0.000",
    }));
    order.status = "closed_short";
    order.closed_at = new Date(approvedMs + 6 * HOUR).toISOString();
    order.close_remark = "The rest is discontinued; the farmer agreed to the smaller order.";
  }
  return order;
}

function requestIdFor(orderId: string): string {
  return mockUuid(MOCK_ID_SPACE.approval, 60_000 + Number.parseInt(orderId.slice(-12), 16));
}

/** The order number's serial, for the demo's DC and invoice numbers. */
function serialOf(order: OrderWire): number {
  return Number(order.order_no?.split("/").at(-1) ?? "0");
}
