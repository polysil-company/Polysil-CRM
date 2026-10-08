import { z } from "zod";

import { calculateResponseSchema, type CalculateRequest } from "./subsidy.schemas";

/**
 * SUBS-004 … SUBS-008 · Subsidy applications, as the backend serves them
 * (`backend/docs/api/subsidy-applications.md`, handover `subsidy-applications-contract.md`).
 * Money and areas are decimal strings, printed as they come; the stored calculation is never
 * recomputed.
 */

const id = z.string().min(1);
/** A business date, `YYYY-MM-DD`. */
const isoDate = z.iso.date();
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const userRef = z.object({ id, full_name: z.string() });
const ref = z.object({ id, name: z.string() });

export const APPLICATION_STATUSES = ["open", "full_fp_received", "cancelled"] as const;
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export const STAGE_FIELD_TYPES = ["date", "amount", "text"] as const;

/** Up to 40 files per application, each up to 10 MB, judged by content. */
export const APPLICATION_DOCUMENTS_MAX = 40;
export const APPLICATION_DOCUMENT_MAX_BYTES = 10 * 1024 * 1024;
export const APPLICATION_DOCUMENT_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
] as const;

export const APPLICATION_PAGE_SIZE = 25;

// ── the application ──────────────────────────────────────────────────────────────

const stageRefSchema = z.object({
  seq: z.number().int(),
  code: z.string().min(1),
  name: z.string(),
  /** The business date of the latest entry. */
  since: isoDate,
});

const applicationWireSchema = z.object({
  id,
  application_no: z.string().min(1),
  /** The department's registration number: the latest Reg. No. entered at stage 4. */
  reg_no: z.string().nullable(),
  status: z.enum(APPLICATION_STATUSES),
  current_stage: stageRefSchema,
  scheme: z.string(),
  system_type: z.string(),
  category: z.object({ code: z.string(), name: z.string(), pct: decimal }),
  lead: z.object({ id, inquiry_no: z.string() }),
  farmer_name: z.string(),
  mobile: z.string(),
  village: z.string().nullable(),
  survey_no: z.string().nullable(),
  territory: z.object({ id, name: z.string(), level: z.string() }),
  partner: ref.nullable(),
  total_area: decimal,
  group_total_area: decimal.nullable(),
  figures: z.object({ total_cost: decimal, subsidy: decimal, farmer_share: decimal }),
  owner: userRef.nullable(),
  owner_org_unit: ref,
  documents: z.object({
    uploaded: z.number().int().nonnegative(),
    listed: z.number().int().nonnegative(),
  }),
  ageing: z.object({
    days_in_stage: z.number().int(),
    days_since_inward: z.number().int().nullable(),
  }),
  full_fp_received_on: z.string().nullable(),
  created_at: z.string(),
  cancellation: z.object({ reason: z.string() }).nullable(),
});

export type ApplicationWire = z.input<typeof applicationWireSchema>;

const applicationSchema = applicationWireSchema.transform((wire) => ({
  id: wire.id,
  number: wire.application_no,
  regNo: wire.reg_no,
  status: wire.status,
  stage: wire.current_stage,
  scheme: wire.scheme,
  systemType: wire.system_type,
  category: wire.category,
  lead: { id: wire.lead.id, inquiryNo: wire.lead.inquiry_no },
  farmerName: wire.farmer_name,
  mobile: wire.mobile,
  village: wire.village,
  surveyNo: wire.survey_no,
  territory: wire.territory,
  partner: wire.partner,
  totalArea: wire.total_area,
  groupTotalArea: wire.group_total_area,
  figures: {
    totalCost: wire.figures.total_cost,
    subsidy: wire.figures.subsidy,
    farmerShare: wire.figures.farmer_share,
  },
  owner: wire.owner === null ? null : { id: wire.owner.id, name: wire.owner.full_name },
  office: wire.owner_org_unit,
  documents: wire.documents,
  daysInStage: wire.ageing.days_in_stage,
  daysSinceInward: wire.ageing.days_since_inward,
  closedOn: wire.full_fp_received_on,
  createdAt: wire.created_at,
  cancellation: wire.cancellation,
}));

export type Application = z.output<typeof applicationSchema>;

export const applicationResponseSchema = z
  .object({ data: applicationSchema })
  .transform(({ data }) => data);

/** The list's meta carries only the cursor. */
export const applicationPageSchema = z
  .object({
    data: z.array(applicationSchema),
    meta: z.object({ next_cursor: z.string().min(1).nullish() }),
  })
  .transform(({ data, meta }) => ({ items: data, nextCursor: meta.next_cursor ?? null }));

export type ApplicationPage = z.output<typeof applicationPageSchema>;

export interface ApplicationListParams {
  readonly status: ApplicationStatus | null;
  readonly stage: string | null;
  readonly q: string;
  /**
   * A lead's applications. The backend doesn't filter on it yet (BE-023), so the rows are also
   * matched on `lead.id` after they arrive.
   */
  readonly leadId: string | null;
}

/** POST /subsidy-applications */
export interface CreateApplicationRequest {
  readonly lead_id: string;
  readonly category_code: string;
  /** Exactly the body sent to POST /subsidy/calculate; the backend runs it again and stores it. */
  readonly calculation: CalculateRequest;
  readonly survey_no: string | null;
}

/** GET /subsidy-applications/{id}/calculation — the calculator's shape, as stored. */
export const storedCalculationSchema = calculateResponseSchema;

// ── stages ───────────────────────────────────────────────────────────────────────

const stageFieldSchema = z.object({
  key: z.string().min(1),
  label: z.string(),
  type: z.enum(STAGE_FIELD_TYPES),
  required: z.boolean(),
});

export type StageField = z.infer<typeof stageFieldSchema>;

const stageDefSchema = z.object({
  seq: z.number().int(),
  code: z.string().min(1),
  name: z.string(),
  fields: z.array(stageFieldSchema),
});

export type StageDef = z.infer<typeof stageDefSchema>;

export const stageDefsSchema = z
  .object({ data: z.array(stageDefSchema) })
  .transform(({ data }) => [...data].sort((a, b) => a.seq - b.seq));

const stageEntryWireSchema = z.object({
  id,
  stage: stageRefSchema,
  occurred_on: isoDate,
  /** Dates as ISO dates, amounts as decimal strings, text as given; null when cleared. */
  values: z.record(z.string(), z.string().nullable()),
  remark: z.string().nullable(),
  entered_by: userRef.nullable(),
  entered_at: z.string(),
});

export type StageEntryWire = z.input<typeof stageEntryWireSchema>;

export const stageEntriesSchema = z
  .object({ data: z.array(stageEntryWireSchema) })
  .transform(({ data }) =>
    data.map((entry) => ({
      id: entry.id,
      stage: entry.stage,
      occurredOn: entry.occurred_on,
      values: entry.values,
      remark: entry.remark,
      enteredBy:
        entry.entered_by === null
          ? null
          : { id: entry.entered_by.id, name: entry.entered_by.full_name },
      enteredAt: entry.entered_at,
    })),
  );

export type StageEntry = z.output<typeof stageEntriesSchema>[number];

/** POST /subsidy-applications/{id}/stages. Every value is a string or null — never a number. */
export interface RecordStageRequest {
  readonly stage_code: string;
  readonly occurred_on: string;
  readonly values: Readonly<Record<string, string | null>>;
  /** Required going back, or recording the current stage again. */
  readonly remark: string | null;
}

/** POST /subsidy-applications/{id}/cancel */
export interface CancelApplicationRequest {
  readonly reason: string;
}

// ── documents ────────────────────────────────────────────────────────────────────

const documentTypeSchema = z.object({
  id,
  code: z.string().min(1),
  name: z.string(),
  is_active: z.boolean(),
});

const documentWireSchema = z.object({
  id,
  content_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  filename: z.string().nullable(),
  uploaded_by: userRef.nullable(),
  created_at: z.string(),
});

export type ApplicationDocumentWire = z.input<typeof documentWireSchema>;

export const checklistSchema = z
  .object({
    data: z.array(z.object({ type: documentTypeSchema, files: z.array(documentWireSchema) })),
  })
  .transform(({ data }) =>
    data.map((item) => ({
      code: item.type.code,
      name: item.type.name,
      active: item.type.is_active,
      files: item.files.map((file) => ({
        id: file.id,
        contentType: file.content_type,
        sizeBytes: file.size_bytes,
        filename: file.filename ?? "Unnamed file",
        uploadedBy:
          file.uploaded_by === null
            ? null
            : { id: file.uploaded_by.id, name: file.uploaded_by.full_name },
        uploadedAt: file.created_at,
      })),
    })),
  );

export type ChecklistItem = z.output<typeof checklistSchema>[number];
export type ApplicationDocument = ChecklistItem["files"][number];

/** POST …/documents answers the stored file; its shape is not read beyond the envelope. */
export const uploadedDocumentSchema = z.object({ data: documentWireSchema });

export const documentLinkSchema = z
  .object({ data: z.object({ url: z.string().min(1), expires_at: z.string() }) })
  .transform(({ data }) => ({ url: data.url, expiresAt: data.expires_at }));

export type DocumentLink = z.output<typeof documentLinkSchema>;
