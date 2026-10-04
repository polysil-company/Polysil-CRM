import { z } from "zod";

import { approvalBlockSchema } from "@/features/orders/api/orders.schemas";
import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

/**
 * Complaints (CMPL-001…009), from the backend's `Complaint`, `ComplaintSummary`, `Stats`,
 * `ComplaintCreate`, `CheckIn`, `QcIn` and `RemedyIn` (backend/docs/api/complaints.md, and the
 * handovers complaints-contract.md and complaint-remedies-contract.md).
 *
 * `draft` → submit → `submitted` → the manager's check: `return` (back to draft) or `approve`
 * (`under_qc`) → QC: `qc_approved` or `qc_rejected` (closed). After `qc_approved`, QC chooses a
 * remedy: `remedy_pending` → `closed`. The raiser can cancel a draft or a submitted one.
 */

export const COMPLAINT_STATUSES = [
  "draft",
  "submitted",
  "under_qc",
  "qc_approved",
  "qc_rejected",
  "remedy_pending",
  "closed",
  "cancelled",
] as const;
export type ComplaintStatus = (typeof COMPLAINT_STATUSES)[number];

export const COMPLAINT_SEVERITIES = ["low", "medium", "high"] as const;
export type ComplaintSeverity = (typeof COMPLAINT_SEVERITIES)[number];

export const ATTACHMENT_KINDS = ["photo", "document", "challan"] as const;

export const REMEDY_KINDS = ["refund", "replacement", "none"] as const;

/** The backend's limits. */
export const COMPLAINT_LINES_MAX = 20;

const isoDateTime = z.iso.datetime({ offset: true });
const isoDate = z.iso.date();
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const id = z.string().min(1);

const userRef = z
  .object({ id, full_name: z.string() })
  .transform((user) => ({ id: user.id, name: user.full_name.trim() || "Unknown" }));
const ref = z.object({ id, name: z.string() });

const leadLink = z
  .object({
    id,
    hidden: z.boolean().optional(),
    inquiry_no: z.string().nullish(),
    farmer_name: z.string().nullish(),
  })
  .transform((lead) => ({
    id: lead.id,
    hidden: lead.hidden ?? false,
    inquiryNo: lead.inquiry_no ?? null,
    farmerName: lead.farmer_name?.trim() || null,
  }));

const partnerLink = z
  .object({
    id,
    hidden: z.boolean().optional(),
    name: z.string().nullish(),
    partner_type: z.string().nullish(),
  })
  .transform((partner) => ({
    id: partner.id,
    hidden: partner.hidden ?? false,
    name: partner.name?.trim() || null,
    partnerType: partner.partner_type ?? null,
  }));

const orderLink = z
  .object({ id, hidden: z.boolean().optional(), order_no: z.string().nullish() })
  .transform((order) => ({
    id: order.id,
    hidden: order.hidden ?? false,
    orderNo: order.order_no ?? null,
  }));

const typeRef = z.object({ id, code: z.string(), name: z.string() });

const lineWireSchema = z.object({
  id,
  product: z.object({ id, description: z.string().nullable() }),
  uom: z.string().nullable(),
  supplied_qty: decimal,
  defective_qty: decimal,
  failure_frequency: z.string().nullable(),
  remark: z.string().nullable(),
});

const attachmentWireSchema = z.object({
  id,
  kind: z.enum(ATTACHMENT_KINDS),
  filename: z.string(),
  content_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  /** False for HEIC: show a file icon, not a thumbnail. */
  preview: z.boolean(),
  uploaded_by: userRef.nullable(),
  uploaded_at: isoDateTime,
});

const checkWireSchema = z.object({
  decision: z.enum(["approve", "return"]),
  remark: z.string(),
  /** Null for a dealer. */
  by: userRef.nullable(),
  at: isoDateTime,
  /** Staff only; absent for a dealer. */
  internal_note: z.string().nullish(),
});

const qualityWireSchema = z.object({
  verdict: z.enum(["approved", "rejected"]),
  remark: z.string(),
  sample_received_on: isoDate.nullable(),
  tested_on: isoDate.nullable(),
  field_visit_on: isoDate.nullable(),
  by: userRef.nullable(),
  at: isoDateTime,
  internal_note: z.string().nullish(),
});

const slaWireSchema = z.object({
  /** `none`: no target applies — show "no target", never red. */
  policy: z.enum(["set", "none"]),
  response_due_at: isoDateTime.nullable(),
  responded_at: isoDateTime.nullable(),
  response_breached: z.boolean(),
  resolution_due_at: isoDateTime.nullable(),
  resolved_at: isoDateTime.nullable(),
  resolution_breached: z.boolean(),
});

const remedyWireSchema = z.object({
  id,
  kind: z.enum(REMEDY_KINDS),
  status: z.enum(["pending", "completed", "rejected", "withdrawn", "cancelled"]),
  /** Null for a dealer. */
  remark: z.string().nullable(),
  refund: z
    .object({
      amount: decimal,
      payee_name: z.string().nullable(),
      paid_through: ref.nullable(),
      approval: approvalBlockSchema.nullable(),
      payment_reference: z.string().nullable(),
    })
    .nullable(),
  replacement: z
    .object({
      order: z.object({ id, order_no: z.string().nullable(), status: z.string() }).nullable(),
    })
    .nullable(),
  chosen_by: userRef.nullable(),
  chosen_at: isoDateTime,
  completed_at: isoDateTime.nullable(),
});

const canWireSchema = z.object({
  edit: z.boolean(),
  submit: z.boolean(),
  check: z.boolean(),
  qc: z.boolean(),
  cancel: z.boolean(),
  delete: z.boolean(),
  upload: z.boolean().optional(),
  remedy: z.boolean().optional(),
  withdraw: z.boolean().optional(),
});

export const complaintWireSchema = z.object({
  doc_type: z.literal("complaint").optional(),
  id,
  /** Null until the first submit. */
  complaint_no: z.string().nullable(),
  status: z.enum(COMPLAINT_STATUSES),
  complaint_type: typeRef,
  severity: z.enum(COMPLAINT_SEVERITIES),
  description: z.string(),
  contact_name: z.string(),
  contact_mobile: z.string(),
  territory: ref,
  partner: partnerLink.nullable(),
  lead: leadLink.nullable(),
  sales_order: orderLink.nullable(),
  dc_no: z.string().nullable(),
  supply_date: isoDate.nullable(),
  reg_no: z.string().nullable(),
  pims_no: z.string().nullable(),
  sample_courier_date: isoDate.nullable(),
  sample_courier_detail: z.string().nullable(),
  lines: z.array(lineWireSchema),
  attachments: z.array(attachmentWireSchema),
  /** The manager's decision since the latest submit. */
  check: checkWireSchema.nullable(),
  quality: qualityWireSchema.nullable(),
  cancellation: z.object({ reason: z.string(), by: userRef.nullable(), at: isoDateTime }).nullish(),
  /** Null before the first submit. */
  sla: slaWireSchema.nullable(),
  submit_count: z.number().int().nonnegative(),
  owner: userRef.nullable(),
  owner_org_unit: ref,
  raised_by: userRef.nullable(),
  remedy: remedyWireSchema.nullish(),
  closed_at: isoDateTime.nullish(),
  can: canWireSchema,
  created_at: isoDateTime,
  updated_at: isoDateTime,
  submitted_at: isoDateTime.nullable(),
});

/** The backend's JSON for one complaint, as the mock backend must produce it. */
export type ComplaintWire = z.input<typeof complaintWireSchema>;

export const complaintSchema = complaintWireSchema.transform((wire) => ({
  id: wire.id,
  number: wire.complaint_no,
  status: wire.status,
  type: wire.complaint_type,
  severity: wire.severity,
  description: wire.description.trim(),
  contactName: wire.contact_name.trim() || "Unnamed contact",
  contactMobile: wire.contact_mobile,
  territory: wire.territory,
  partner: wire.partner,
  lead: wire.lead,
  salesOrder: wire.sales_order,
  dcNo: wire.dc_no,
  supplyDate: wire.supply_date,
  regNo: wire.reg_no,
  pimsNo: wire.pims_no,
  sampleCourierDate: wire.sample_courier_date,
  sampleCourierDetail: wire.sample_courier_detail,
  lines: wire.lines.map((line) => ({
    id: line.id,
    product: { id: line.product.id, description: line.product.description ?? "A product" },
    uom: line.uom,
    suppliedQty: line.supplied_qty,
    defectiveQty: line.defective_qty,
    failureFrequency: line.failure_frequency,
    remark: line.remark,
  })),
  attachments: wire.attachments.map((attachment) => ({
    id: attachment.id,
    kind: attachment.kind,
    filename: attachment.filename,
    contentType: attachment.content_type,
    sizeBytes: attachment.size_bytes,
    preview: attachment.preview,
    uploadedBy: attachment.uploaded_by,
    uploadedAt: attachment.uploaded_at,
  })),
  check:
    wire.check === null
      ? null
      : {
          decision: wire.check.decision,
          remark: wire.check.remark,
          by: wire.check.by,
          at: wire.check.at,
          internalNote: wire.check.internal_note ?? null,
        },
  quality:
    wire.quality === null
      ? null
      : {
          verdict: wire.quality.verdict,
          remark: wire.quality.remark,
          sampleReceivedOn: wire.quality.sample_received_on,
          testedOn: wire.quality.tested_on,
          fieldVisitOn: wire.quality.field_visit_on,
          by: wire.quality.by,
          at: wire.quality.at,
          internalNote: wire.quality.internal_note ?? null,
        },
  cancellation: wire.cancellation ?? null,
  sla:
    wire.sla === null
      ? null
      : {
          policy: wire.sla.policy,
          responseDueAt: wire.sla.response_due_at,
          respondedAt: wire.sla.responded_at,
          responseBreached: wire.sla.response_breached,
          resolutionDueAt: wire.sla.resolution_due_at,
          resolvedAt: wire.sla.resolved_at,
          resolutionBreached: wire.sla.resolution_breached,
        },
  submitCount: wire.submit_count,
  owner: wire.owner,
  ownerOrgUnit: wire.owner_org_unit,
  raisedBy: wire.raised_by,
  remedy:
    wire.remedy == null
      ? null
      : {
          id: wire.remedy.id,
          kind: wire.remedy.kind,
          status: wire.remedy.status,
          remark: wire.remedy.remark,
          refund:
            wire.remedy.refund === null
              ? null
              : {
                  amount: wire.remedy.refund.amount,
                  payeeName: wire.remedy.refund.payee_name,
                  paidThrough: wire.remedy.refund.paid_through,
                  approval: wire.remedy.refund.approval,
                  paymentReference: wire.remedy.refund.payment_reference,
                },
          replacementOrder:
            wire.remedy.replacement?.order == null
              ? null
              : {
                  id: wire.remedy.replacement.order.id,
                  orderNo: wire.remedy.replacement.order.order_no,
                  status: wire.remedy.replacement.order.status,
                },
          chosenBy: wire.remedy.chosen_by,
          chosenAt: wire.remedy.chosen_at,
          completedAt: wire.remedy.completed_at,
        },
  closedAt: wire.closed_at ?? null,
  can: {
    edit: wire.can.edit,
    submit: wire.can.submit,
    check: wire.can.check,
    qc: wire.can.qc,
    cancel: wire.can.cancel,
    delete: wire.can.delete,
    upload: wire.can.upload ?? false,
    remedy: wire.can.remedy ?? false,
    withdraw: wire.can.withdraw ?? false,
  },
  createdAt: wire.created_at,
  submittedAt: wire.submitted_at,
}));

export type Complaint = z.output<typeof complaintSchema>;

export const complaintResponseSchema = z
  .object({ data: complaintSchema })
  .transform(({ data }) => data);

// ── the list (CMPL-001) ───────────────────────────────────────────────────────────

const summaryWireSchema = z.object({
  id,
  complaint_no: z.string().nullable(),
  status: z.enum(COMPLAINT_STATUSES),
  complaint_type: typeRef,
  severity: z.enum(COMPLAINT_SEVERITIES),
  contact_name: z.string(),
  partner: partnerLink.nullable(),
  owner: userRef.nullable(),
  first_submitted_at: isoDateTime.nullable(),
  /** Either target missed. */
  breached: z.boolean(),
  created_at: isoDateTime,
});

export type ComplaintSummaryWire = z.input<typeof summaryWireSchema>;

const summarySchema = summaryWireSchema.transform((wire) => ({
  id: wire.id,
  number: wire.complaint_no,
  status: wire.status,
  type: wire.complaint_type,
  severity: wire.severity,
  contactName: wire.contact_name.trim() || "Unnamed contact",
  partner: wire.partner,
  owner: wire.owner,
  firstSubmittedAt: wire.first_submitted_at,
  breached: wire.breached,
  createdAt: wire.created_at,
}));

export type ComplaintSummary = z.output<typeof summarySchema>;

/** GET /complaints — one row at a time, so one odd row never blanks the list. */
export const complaintPageSchema = cursorPageSchema(summarySchema);
export type ComplaintPage = CursorPage<ComplaintSummary>;
export type ComplaintPageWire = { data: ComplaintSummaryWire[]; meta: PageMetaWire };

export const COMPLAINT_PAGE_SIZE = 25;

export interface ComplaintListParams {
  readonly status: readonly ComplaintStatus[];
  readonly severity: ComplaintSeverity | null;
  readonly typeId: string | null;
  readonly q: string;
  readonly breached: boolean;
  readonly noOwner: boolean;
  /** Waiting for the user's check or QC verdict, oldest first; one page. */
  readonly awaitingMe: boolean;
  readonly leadId: string | null;
  readonly orderId: string | null;
}

/** GET /complaints/stats */
export const complaintStatsSchema = z
  .object({
    data: z.object({
      by_status: z.record(z.string(), z.number().int().nonnegative()),
      breached: z.number().int().nonnegative(),
      no_target: z.number().int().nonnegative(),
      /** False: hide the upload button. */
      storage_available: z.boolean(),
    }),
  })
  .transform(({ data }) => ({
    byStatus: data.by_status,
    breached: data.breached,
    noTarget: data.no_target,
    storageAvailable: data.storage_available,
  }));

export type ComplaintStats = z.output<typeof complaintStatsSchema>;
export type ComplaintStatsWire = z.input<typeof complaintStatsSchema>;

/** GET /complaints/{id}/assignees — the owner picker in the check dialog. */
export const complaintAssigneesSchema = z
  .object({
    data: z.array(z.object({ id, full_name: z.string(), org_unit_id: z.string().nullable() })),
  })
  .transform(({ data }) =>
    data.map((person) => ({ id: person.id, name: person.full_name.trim() || "Unnamed" })),
  );

export type ComplaintAssignee = z.output<typeof complaintAssigneesSchema>[number];

// ── requests ──────────────────────────────────────────────────────────────────────

const lineInSchema = z.object({
  product_id: z.string().min(1),
  supplied_qty: z.string().min(1),
  defective_qty: z.string().min(1),
  failure_frequency: z.string().nullish(),
  remark: z.string().nullish(),
});

const headerFields = {
  description: z.string().min(1),
  contact_name: z.string().min(1),
  contact_mobile: z.string().min(1),
  territory_id: z.string().min(1),
  partner_id: z.string().nullish(),
  lead_id: z.string().nullish(),
  sales_order_id: z.string().nullish(),
  dc_no: z.string().nullish(),
  supply_date: isoDate.nullish(),
  reg_no: z.string().nullish(),
  pims_no: z.string().nullish(),
  sample_courier_date: isoDate.nullish(),
  sample_courier_detail: z.string().nullish(),
  complaint_type_id: z.string().min(1),
  severity: z.enum(COMPLAINT_SEVERITIES).optional(),
};

/** POST /complaints — a draft, 1 to 20 lines. */
export const createComplaintRequestSchema = z.object({
  ...headerFields,
  lines: z.array(lineInSchema).min(1).max(COMPLAINT_LINES_MAX),
});
export type CreateComplaintRequest = z.infer<typeof createComplaintRequestSchema>;

/** PATCH /complaints/{id} — a draft's header. */
export const patchComplaintRequestSchema = z.object(headerFields).partial();
export type PatchComplaintRequest = z.infer<typeof patchComplaintRequestSchema>;

/** PUT /complaints/{id}/lines */
export const replaceLinesRequestSchema = z.object({
  lines: z.array(lineInSchema).min(1).max(COMPLAINT_LINES_MAX),
});
export type ReplaceLinesRequest = z.infer<typeof replaceLinesRequestSchema>;

/** POST /complaints/{id}/check — severity and owner with approve only. */
export const checkRequestSchema = z.object({
  decision: z.enum(["approve", "return"]),
  remark: z.string().min(1),
  severity: z.enum(COMPLAINT_SEVERITIES).nullish(),
  owner_user_id: z.string().nullish(),
  internal_note: z.string().nullish(),
});
export type CheckRequest = z.infer<typeof checkRequestSchema>;

/** POST /complaints/{id}/qc */
export const qcRequestSchema = z.object({
  verdict: z.enum(["approved", "rejected"]),
  remark: z.string().min(1),
  sample_received_on: isoDate.nullish(),
  tested_on: isoDate.nullish(),
  field_visit_on: isoDate.nullish(),
  internal_note: z.string().nullish(),
});
export type QcRequest = z.infer<typeof qcRequestSchema>;

/** POST /complaints/{id}/cancel */
export const cancelComplaintRequestSchema = z.object({ reason: z.string().min(1) });
export type CancelComplaintRequest = z.infer<typeof cancelComplaintRequestSchema>;

// TODO(CMPL-006, CMPL-007): the remedy, withdraw and attachment-link requests come with C2.
