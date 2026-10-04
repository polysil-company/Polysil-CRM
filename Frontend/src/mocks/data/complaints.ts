import type {
  ComplaintSeverity,
  ComplaintStatus,
  ComplaintWire,
} from "@/features/complaints/api/complaints.schemas";
import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import { todayInIndia } from "@/lib/format";

import { mockLookupRows } from "./lookups";
import { MOCK_PRODUCTS } from "./quotations";
import { createRandom } from "./random";
import { MOCK_ID_SPACE, MOCK_PARTNERS, MOCK_STAFF, mockUuid } from "./reference";
import { MOCK_TERRITORIES } from "./territories";

/** A complaint as the mock keeps it: `can` is worked out per caller when it is served. */
export type MockComplaint = Omit<ComplaintWire, "can">;

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

/** The backend's stand-in targets, in hours (GAP-147): response, resolution. */
export const MOCK_SLA_HOURS: Readonly<Record<ComplaintSeverity, readonly [number, number]>> = {
  high: [4, 18],
  medium: [8, 27],
  low: [9, 45],
};

const DESCRIPTIONS = [
  "Laterals cracking within two months of installation.",
  "Drippers clogging in one block; flow down by half.",
  "Filter housing leaking at the joint.",
  "Short supply: two rolls of lateral missing from the delivery.",
  "Sprinkler risers bent on arrival.",
] as const;

const PEOPLE = [
  ["Kiritbhai Shah", "+919876543210"],
  ["Jayesh Patel", "+919825011223"],
  ["Mukesh Rabari", "+919898776655"],
  ["Hansaben Dabhi", "+919712345678"],
  ["Ramesh Vaghela", "+919909090909"],
] as const;

/** When an SLA target falls due: the backend counts working hours; the mock counts plain ones. */
export function slaFor(
  severity: ComplaintSeverity,
  submittedAt: number,
  respondedAt: number | null,
  resolvedAt: number | null,
  now: number,
): NonNullable<ComplaintWire["sla"]> {
  const [response, resolution] = MOCK_SLA_HOURS[severity];
  const responseDue = submittedAt + response * HOUR * 2;
  const resolutionDue = submittedAt + resolution * HOUR * 2;
  return {
    policy: "set",
    response_due_at: new Date(responseDue).toISOString(),
    responded_at: respondedAt === null ? null : new Date(respondedAt).toISOString(),
    response_breached: (respondedAt ?? now) > responseDue,
    resolution_due_at: new Date(resolutionDue).toISOString(),
    resolved_at: resolvedAt === null ? null : new Date(resolvedAt).toISOString(),
    resolution_breached: (resolvedAt ?? now) > resolutionDue,
  };
}

/**
 * Seeded complaints, one or more in every status: drafts, a returned one, some waiting on a
 * manager's check (one late), some with QC, approved and rejected verdicts, and a cancelled one.
 * Numbered `Poly/Comp./2026-27/GJ/NN` once submitted.
 */
export function generateComplaints(
  leads: readonly LeadWire[],
  orders: readonly OrderWire[],
  now: number = Date.now(),
): MockComplaint[] {
  const random = createRandom(0xc0a1);
  const types = mockLookupRows("complaint-types");
  const talukas = MOCK_TERRITORIES.filter((territory) => territory.level === "taluka");
  const manager = MOCK_STAFF[1];
  const qc = MOCK_STAFF[4];
  const plan: readonly (readonly [ComplaintStatus, ComplaintSeverity, number])[] = [
    ["draft", "medium", 0.2],
    ["draft", "low", 1],
    ["submitted", "high", 0.4],
    ["submitted", "medium", 3],
    ["submitted", "low", 1.2],
    ["under_qc", "medium", 4],
    ["under_qc", "high", 2],
    ["qc_approved", "medium", 9],
    ["qc_rejected", "low", 12],
    ["cancelled", "medium", 6],
    ["draft", "medium", 5],
  ];
  let serial = 0;

  return plan.map(([status, severity, ageDays], index) => {
    const created = now - ageDays * DAY - random.int(1, 8) * HOUR;
    const submitted = status === "draft" ? null : created + HOUR;
    const lead = leads[index * 3];
    const order = index % 3 === 0 ? orders.find((item) => item.dispatches.length > 0) : undefined;
    const [contact, mobile] = PEOPLE[index % PEOPLE.length] ?? PEOPLE[0];
    const raiser = MOCK_STAFF[(index % 3) + 2] ?? MOCK_STAFF[0];
    const territory = talukas[index % talukas.length];
    const partner = MOCK_PARTNERS[index % MOCK_PARTNERS.length];
    const type = types[index % types.length];
    const returned = index === 10; // a draft the manager sent back
    const checked = status === "under_qc" || status.startsWith("qc_");
    const respondedAt = submitted === null || status === "submitted" ? null : submitted + 3 * HOUR;
    const resolvedAt =
      status === "qc_approved" || status === "qc_rejected"
        ? submitted === null
          ? null
          : submitted + 2 * DAY
        : null;
    const number =
      submitted === null && !returned
        ? null
        : `Poly/Comp./2026-27/GJ/${String((serial += 1)).padStart(2, "0")}`;
    const lineProducts = [
      MOCK_PRODUCTS[index % MOCK_PRODUCTS.length],
      MOCK_PRODUCTS[(index + 2) % MOCK_PRODUCTS.length],
    ];

    return {
      id: mockUuid(MOCK_ID_SPACE.complaint, index + 1),
      complaint_no: number,
      status,
      complaint_type:
        type === undefined
          ? { id: "t", code: "dripline", name: "Dripline / Lateral / PVC" }
          : { id: type.id, code: type.code, name: type.name },
      severity,
      description: DESCRIPTIONS[index % DESCRIPTIONS.length] ?? DESCRIPTIONS[0],
      contact_name: contact,
      contact_mobile: mobile,
      territory: { id: territory?.id ?? "t-1", name: territory?.name ?? "Gondal" },
      partner:
        partner === undefined
          ? null
          : {
              id: partner.id,
              hidden: false,
              name: partner.name,
              partner_type: partner.partner_type,
            },
      lead:
        lead === undefined
          ? null
          : {
              id: lead.id,
              hidden: false,
              inquiry_no: lead.inquiry_no,
              farmer_name: lead.farmer_name,
            },
      sales_order:
        order === undefined ? null : { id: order.id, hidden: false, order_no: order.order_no },
      dc_no: status === "draft" && index === 0 ? null : `DC-${String(4400 + index)}`,
      supply_date:
        status === "draft" && index === 0 ? null : todayInIndia(new Date(created - 60 * DAY)),
      reg_no: null,
      pims_no: null,
      sample_courier_date: checked ? todayInIndia(new Date(created + DAY)) : null,
      sample_courier_detail: checked ? "DTDC, docket 7781234" : null,
      lines: lineProducts.flatMap((product, lineIndex) =>
        product === undefined
          ? []
          : [
              {
                id: mockUuid(MOCK_ID_SPACE.complaint, 1000 + index * 10 + lineIndex),
                product: { id: product.id, description: product.name },
                uom: product.uom,
                supplied_qty: product.uomDecimals > 0 ? "2000.00" : "40",
                defective_qty: product.uomDecimals > 0 ? "340.00" : String(lineIndex === 0 ? 6 : 0),
                failure_frequency: lineIndex === 0 ? "every 3 to 4 m" : null,
                remark: null,
              },
            ],
      ),
      attachments: [],
      check: returned
        ? {
            decision: "return",
            remark: "Add the supply date from the challan, and a photo of the cracked lateral.",
            by: manager ?? null,
            at: new Date(created + 5 * HOUR).toISOString(),
            internal_note: null,
          }
        : checked
          ? {
              decision: "approve",
              remark: "Genuine; sample sent to QC.",
              by: manager ?? null,
              at: new Date((submitted ?? created) + 3 * HOUR).toISOString(),
              internal_note: "Repeat issue in this taluka.",
            }
          : null,
      quality:
        status === "qc_approved" || status === "qc_rejected"
          ? {
              verdict: status === "qc_approved" ? "approved" : "rejected",
              remark:
                status === "qc_approved"
                  ? "Manufacturing defect in the wall thickness."
                  : "Damage from rodents in the field, not a defect.",
              sample_received_on: todayInIndia(new Date(created + 2 * DAY)),
              tested_on: todayInIndia(new Date(created + 3 * DAY)),
              field_visit_on: null,
              by: qc ?? null,
              at: new Date(created + 3 * DAY).toISOString(),
              internal_note: null,
            }
          : null,
      cancellation:
        status === "cancelled"
          ? {
              reason: "Raised twice by mistake.",
              by: raiser ?? null,
              at: new Date(created + 2 * HOUR).toISOString(),
            }
          : null,
      sla: submitted === null ? null : slaFor(severity, submitted, respondedAt, resolvedAt, now),
      submit_count: submitted === null ? (returned ? 1 : 0) : 1,
      owner: checked ? (raiser ?? null) : null,
      owner_org_unit: { id: "ou-vadodara", name: "Vadodara District" },
      raised_by: raiser ?? null,
      remedy: null,
      closed_at: null,
      created_at: new Date(created).toISOString(),
      updated_at: new Date(submitted ?? created).toISOString(),
      submitted_at: submitted === null ? null : new Date(submitted).toISOString(),
    };
  });
}
