import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type {
  QuotationLineWire,
  QuotationStatus,
  QuotationSummaryWire,
  QuotationWire,
} from "@/features/quotations/api/quotations.schemas";

import { createRandom, type Random } from "./random";
import { MOCK_ID_SPACE, mockUuid } from "./reference";

const DAY = 24 * 60 * 60 * 1000;
const VALIDITY_DAYS = 45;

/** A handful of the client's products, with the HSN and slab the price list carries. */
const MOCK_PRODUCTS = [
  {
    name: "UPVC PIPE 90 MM 4 KG/CM2 CLASS - 2 IS: 4985",
    hsn: "3917",
    uom: "MTR",
    rate: 10319,
    slab: 18,
  },
  { name: "HDPE LATERAL 16 MM 2.5 KG/CM2", hsn: "3917", uom: "MTR", rate: 1450, slab: 12 },
  { name: "INLINE DRIPPER 4 LPH", hsn: "8424", uom: "NOS", rate: 380, slab: 12 },
  { name: "SCREEN FILTER 2 INCH 20 M3/HR", hsn: "8421", uom: "NOS", rate: 485000, slab: 18 },
  { name: "VENTURI INJECTOR 1.5 INCH", hsn: "8424", uom: "NOS", rate: 129000, slab: 12 },
  { name: "SPRINKLER SET 1 INCH WITH RISER", hsn: "8424", uom: "SET", rate: 86000, slab: 12 },
] as const;

export const MOCK_SELLER = {
  id: mockUuid(MOCK_ID_SPACE.quotation, 1),
  gstin: "24AAACP1234A1Z5",
  legal_name: "Polysil Irrigation Systems Pvt Ltd",
  address: "GIDC Estate, Vadodara, Gujarat",
  state: "GJ",
} as const;

const PRICE_LIST = { id: mockUuid(MOCK_ID_SPACE.quotation, 2), name: "GJ 2026-27" } as const;

// ── money in whole paise, as the backend works it out ────────────────────────

function paise(value: number): string {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  return `${sign}${String(Math.trunc(abs / 100))}.${String(abs % 100).padStart(2, "0")}`;
}

/** A rate or percentage at three places, as the backend sends it: 9 → "9.000", 2.5 → "2.500". */
function rate3(value: number): string {
  return value.toFixed(3);
}

/** `part` percent of `amount` paise, rounded half up to the paisa. */
function percentOf(amount: number, percent: number): number {
  return Math.round((amount * percent) / 100);
}

/**
 * One priced line: gross, three discount tiers each on the running balance and each
 * rounded before the next, then GST split into CGST and SGST within the state.
 */
export function mockLine(
  lineNo: number,
  product: (typeof MOCK_PRODUCTS)[number],
  qty: number,
  discounts: readonly [number, number, number],
  provisional: boolean,
): QuotationLineWire {
  const gross = product.rate * qty;
  const d1 = percentOf(gross, discounts[0]);
  const after1 = gross - d1;
  const d2 = percentOf(after1, discounts[1]);
  const after2 = after1 - d2;
  const d3 = percentOf(after2, discounts[2]);
  const taxable = after2 - d3;
  const cgst = percentOf(taxable, product.slab / 2);
  const sgst = percentOf(taxable, product.slab / 2);

  return {
    line_no: lineNo,
    product_id: mockUuid(MOCK_ID_SPACE.quotation, 100 + MOCK_PRODUCTS.indexOf(product)),
    description: product.name,
    hsn_code: product.hsn,
    uom: product.uom,
    qty: `${String(qty)}.000`,
    rate: paise(product.rate),
    gross: paise(gross),
    discount_pct: rate3(discounts[0]),
    discount1_amt: paise(d1),
    after_discount1: paise(after1),
    discount2_pct: rate3(discounts[1]),
    discount2_amt: paise(d2),
    after_discount2: paise(after2),
    discount3_pct: rate3(discounts[2]),
    discount3_amt: paise(d3),
    discount: paise(d1 + d2 + d3),
    taxable: paise(taxable),
    gst_slab: rate3(product.slab),
    cgst_rate: rate3(product.slab / 2),
    sgst_rate: rate3(product.slab / 2),
    igst_rate: "0.000",
    cgst: paise(cgst),
    sgst: paise(sgst),
    igst: "0.00",
    total: paise(taxable + cgst + sgst),
    price_list_id: PRICE_LIST.id,
    price_list_item_id: mockUuid(MOCK_ID_SPACE.quotation, 200 + MOCK_PRODUCTS.indexOf(product)),
    gst_rate_id: mockUuid(MOCK_ID_SPACE.quotation, 300 + product.slab),
    provisional_fields: provisional ? ["rate"] : [],
  };
}

function sumField(lines: readonly QuotationLineWire[], field: keyof QuotationLineWire): string {
  const total = lines.reduce((sum, line) => {
    const value = line[field];
    return typeof value === "string" ? sum + Math.round(Number(value) * 100) : sum;
  }, 0);
  return paise(total);
}

export function totalsOf(lines: readonly QuotationLineWire[]): QuotationWire["totals"] {
  return {
    gross: sumField(lines, "gross"),
    discount: sumField(lines, "discount"),
    taxable: sumField(lines, "taxable"),
    cgst: sumField(lines, "cgst"),
    sgst: sumField(lines, "sgst"),
    igst: "0.00",
    total: sumField(lines, "total"),
  };
}

function isoDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

function pickLines(random: Random, provisional: boolean): QuotationLineWire[] {
  const count = random.int(1, 4);
  const start = random.int(0, MOCK_PRODUCTS.length - count);
  const chosen = MOCK_PRODUCTS.slice(start, start + count);
  return chosen.map((product, index) =>
    mockLine(
      index + 1,
      product,
      product.uom === "MTR" ? random.int(50, 900) : random.int(1, 40),
      [random.pick([0, 5, 10]), random.pick([0, 0, 2, 5]), random.pick([0, 0, 0, 1])],
      provisional && index === 0,
    ),
  );
}

interface QuotationSeed {
  readonly lead: LeadWire;
  readonly status: QuotationStatus;
  readonly version: number;
  readonly number: number | null;
  readonly createdAt: number;
  readonly pdfState: "pending" | "ready" | "failed";
}

function buildQuotation(seed: QuotationSeed, index: number, random: Random): QuotationWire {
  const { lead, status } = seed;
  const provisional = random.chance(0.3);
  const lines = pickLines(random, provisional);
  const sent = status !== "draft";
  const sentAt = sent ? seed.createdAt + DAY : null;
  const viewed = ["viewed", "negotiation", "accepted", "rejected"].includes(status);
  const quoteNo =
    seed.number === null ? null : `QT/GJ/2026-27/${String(seed.number).padStart(5, "0")}`;

  return {
    id: mockUuid(MOCK_ID_SPACE.quotation, 10_000 + index),
    quote_no: sent ? quoteNo : null,
    version: seed.version,
    status,
    sales_type: lead.inquiry_type === "industrial" ? "industrial" : "commercial",
    source: "internal",
    lead: { id: lead.id, inquiry_no: lead.inquiry_no, stage: lead.stage },
    party: {
      name: lead.farmer_name,
      mobile: lead.mobile,
      address: [lead.village, lead.territory.name, "Gujarat"].filter(Boolean).join(", "),
      gstin: null,
    },
    partner: lead.assigned_partner,
    owner: lead.owner,
    owner_org_unit: lead.owner_org_unit,
    territory: lead.territory,
    seller_gstin: MOCK_SELLER,
    place_of_supply: { territory: lead.territory, state: "GJ" },
    intra_state: true,
    price_effective_date: isoDate(seed.createdAt),
    price_list: PRICE_LIST,
    price_list_ids: [PRICE_LIST.id],
    lines,
    totals: totalsOf(lines),
    is_provisional: provisional,
    warnings: provisional
      ? [`provisional_pricing: 1 of ${String(lines.length)} lines use stand-in rates or tax slabs`]
      : [],
    terms: "Prices ex-works Vadodara. Delivery within 7 days of order. Installation extra.",
    valid_until: sentAt === null ? null : isoDate(sentAt + VALIDITY_DAYS * DAY),
    sent_at: sentAt === null ? null : new Date(sentAt).toISOString(),
    viewed_at: viewed && sentAt !== null ? new Date(sentAt + DAY / 3).toISOString() : null,
    open_count: viewed ? random.int(1, 5) : 0,
    accepted_at:
      status === "accepted" && sentAt !== null ? new Date(sentAt + 3 * DAY).toISOString() : null,
    rejected_at:
      status === "rejected" && sentAt !== null ? new Date(sentAt + 2 * DAY).toISOString() : null,
    decided_by: status === "accepted" || status === "rejected" ? lead.owner : null,
    decision_remark:
      status === "accepted"
        ? "Confirmed on the phone; wants delivery next week."
        : status === "rejected"
          ? "Found the lateral price high; asked for a revised offer."
          : null,
    supersedes: null,
    superseded_by: null,
    share_url: sent ? `https://crm.polysil.example/q/mock-${String(index)}` : null,
    pdf_state: sent ? seed.pdfState : null,
    pdf_error: sent && seed.pdfState === "failed" ? "The PDF renderer timed out." : null,
    discount: sent
      ? null
      : {
          effective_pct: "7.50",
          owner_limit_pct: "5.00",
          approval_required: true,
          send_gate: "required",
        },
    approval: null,
    created_at: new Date(seed.createdAt).toISOString(),
    created_by: lead.owner,
    updated_at: new Date(sentAt ?? seed.createdAt).toISOString(),
  };
}

/** The quotation status that matches a lead's stage, as sending and deciding move the lead. */
function statusFor(lead: LeadWire, random: Random): QuotationStatus | null {
  switch (lead.stage) {
    case "qualified":
      return random.chance(0.5) ? "draft" : null;
    case "quoted":
      return random.pick(["sent", "viewed", "viewed", "expired"] as const);
    case "negotiation":
      return "negotiation";
    case "won":
      return "accepted";
    default:
      return null;
  }
}

/**
 * QUOT-001, QUOT-002 · Quotations for the seeded leads, newest first: a draft on some qualified
 * leads, a sent or viewed one on quoted leads, one in negotiation — some revised, so version 1
 * is superseded by version 2 — and an accepted one on won leads. A few PDFs are still rendering
 * or failed, so those states can be previewed.
 */
export function generateQuotations(leads: readonly LeadWire[], seed = 20_260_927): QuotationWire[] {
  const random = createRandom(seed);
  const quotations: QuotationWire[] = [];
  let number = 0;

  for (const lead of leads) {
    const status = statusFor(lead, random);
    if (status === null) {
      continue;
    }
    const createdAt = Date.parse(lead.created_at) + 2 * DAY;
    const pdfState = random.chance(0.06) ? "failed" : random.chance(0.06) ? "pending" : "ready";
    const numbered = status === "draft" ? null : (number += 1);
    const revised = status === "negotiation" && random.chance(0.5);

    if (revised) {
      const first = buildQuotation(
        { lead, status: "rejected", version: 1, number: numbered, createdAt, pdfState: "ready" },
        quotations.length,
        random,
      );
      const second = buildQuotation(
        { lead, status, version: 2, number: numbered, createdAt: createdAt + 3 * DAY, pdfState },
        quotations.length + 1,
        random,
      );
      first.superseded_by = { id: second.id, version: 2 };
      second.supersedes = { id: first.id, version: 1 };
      quotations.push(first, second);
    } else {
      quotations.push(
        buildQuotation(
          { lead, status, version: 1, number: numbered, createdAt, pdfState },
          quotations.length,
          random,
        ),
      );
    }
  }

  return quotations.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

/** The list row: the header without lines. */
export function toQuotationSummary(quotation: QuotationWire): QuotationSummaryWire {
  return {
    id: quotation.id,
    quote_no: quotation.quote_no,
    version: quotation.version,
    status: quotation.status,
    sales_type: quotation.sales_type,
    lead: quotation.lead,
    party_name: quotation.party.name,
    party_mobile: quotation.party.mobile,
    partner: quotation.partner,
    owner: quotation.owner,
    totals: quotation.totals,
    is_provisional: quotation.is_provisional,
    valid_until: quotation.valid_until,
    sent_at: quotation.sent_at,
    viewed_at: quotation.viewed_at,
    pdf_state: quotation.pdf_state,
    superseded_by: quotation.superseded_by,
    created_at: quotation.created_at,
  };
}
