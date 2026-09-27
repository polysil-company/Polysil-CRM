import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";
import { normalizeIndianMobile } from "@/lib/format";

/**
 * Leads contract (LEAD-001 … LEAD-004), from the backend's OpenAPI (`Lead`, `LeadPage`,
 * `LeadCreate`) and backend/docs/api/leads.md.
 *
 * The wire format is snake_case inside a `{ data }` envelope; the transforms below turn it
 * into the camelCase shape screens use. The mock backend writes the wire format and is read
 * through these same schemas, so it cannot drift from the contract.
 *
 * Money and the score are decimal strings ("125000.00"). Format them with lib/format and add
 * them with `sumRupees` — never with `+`.
 */

export const LEAD_STAGES = [
  "new",
  "contacted",
  "qualified",
  "quoted",
  "negotiation",
  "won",
  "lost",
  "merged",
  "dormant",
] as const;
export type LeadStage = (typeof LEAD_STAGES)[number];

export const LEAD_INQUIRY_TYPES = ["commercial", "subsidised", "industrial"] as const;
export type LeadInquiryType = (typeof LEAD_INQUIRY_TYPES)[number];

export const LEAD_PRIORITIES = ["hot", "warm", "cold"] as const;
export type LeadPriority = (typeof LEAD_PRIORITIES)[number];

/** What made the backend suspect two leads are the same enquiry. */
export const DUPLICATE_SIGNALS = ["mobile", "email", "name_geo"] as const;
export type DuplicateSignal = (typeof DUPLICATE_SIGNALS)[number];

const DUPLICATE_STATES = ["pending", "merged", "dismissed"] as const;

const isoDateTime = z.iso.datetime({ offset: true });
const refSchema = z.object({ id: z.string().min(1), name: z.string().min(1) });
const userRefSchema = z.object({ id: z.string().min(1), full_name: z.string().min(1) });

/** Every key is always present; null means "not set", never "hidden". */
export const leadWireSchema = z.object({
  id: z.string().min(1),
  /** Human reference, e.g. "POL/GJ/2026-27/00123". */
  inquiry_no: z.string().min(1),
  stage: z.enum(LEAD_STAGES),
  inquiry_type: z.enum(LEAD_INQUIRY_TYPES),
  /** A code from GET /lookups/mis-systems. */
  mis_system: z.string().min(1),
  /** A code from GET /lookups/lead-sources. */
  source: z.string().min(1),
  farmer_name: z.string().min(1),
  /** E.164, e.g. "+919876543210". */
  mobile: z.string().min(1),
  email: z.string().nullable(),
  territory: refSchema.extend({ level: z.string().min(1) }),
  village: z.string().nullable(),
  /** The staff owner; null while the lead waits in the unassigned list. */
  owner: userRefSchema.nullable(),
  owner_org_unit: refSchema,
  assigned_partner: refSchema.extend({ partner_type: z.string().min(1) }).nullable(),
  /** Decimal string; null before the lead is scored. */
  score: z.string().nullable(),
  priority: z.enum(LEAD_PRIORITIES).nullable(),
  /** Rupees, as a decimal string. */
  estimated_value: z.string().nullable(),
  lost_reason: refSchema.extend({ code: z.string().min(1) }).nullable(),
  lost_note: z.string().nullable(),
  reopen_count: z.number().int().nonnegative(),
  /** Set on a merged lead; points at the lead that absorbed it. */
  merged_into: z.object({ id: z.string().min(1), inquiry_no: z.string().min(1) }).nullable(),
  first_contacted_at: isoDateTime.nullable(),
  last_activity_at: isoDateTime,
  created_at: isoDateTime,
  created_by: userRefSchema.nullable(),
  /** Pending duplicate links whose other lead the caller can also see. */
  duplicates: z
    .array(
      z.object({
        link_id: z.string().min(1),
        lead_id: z.string().min(1),
        inquiry_no: z.string().min(1),
        signal: z.enum(DUPLICATE_SIGNALS),
        score: z.string().nullish(),
        state: z.enum(DUPLICATE_STATES),
      }),
    )
    .optional(),
});

/** The backend's JSON for one lead, as the mock backend must produce it. */
export type LeadWire = z.input<typeof leadWireSchema>;

/** One lead, as screens read it. The domain type is inferred from this mapping. */
export const leadSchema = leadWireSchema.transform((wire) => ({
  id: wire.id,
  code: wire.inquiry_no,
  stage: wire.stage,
  type: wire.inquiry_type,
  misSystem: wire.mis_system,
  source: wire.source,
  customerName: wire.farmer_name,
  phone: wire.mobile,
  email: wire.email,
  territory: wire.territory,
  village: wire.village,
  owner: wire.owner ? { id: wire.owner.id, name: wire.owner.full_name } : null,
  ownerOrgUnit: wire.owner_org_unit,
  channelPartner: wire.assigned_partner
    ? {
        id: wire.assigned_partner.id,
        name: wire.assigned_partner.name,
        partnerType: wire.assigned_partner.partner_type,
      }
    : null,
  score: wire.score,
  priority: wire.priority,
  estimatedValue: wire.estimated_value,
  lostReason: wire.lost_reason,
  lostNote: wire.lost_note,
  reopenCount: wire.reopen_count,
  mergedInto: wire.merged_into
    ? { id: wire.merged_into.id, code: wire.merged_into.inquiry_no }
    : null,
  firstContactedAt: wire.first_contacted_at,
  lastActivityAt: wire.last_activity_at,
  createdAt: wire.created_at,
  createdBy: wire.created_by ? { id: wire.created_by.id, name: wire.created_by.full_name } : null,
  duplicates: (wire.duplicates ?? []).map((duplicate) => ({
    linkId: duplicate.link_id,
    leadId: duplicate.lead_id,
    code: duplicate.inquiry_no,
    signal: duplicate.signal,
    score: duplicate.score ?? null,
    state: duplicate.state,
  })),
}));

export type Lead = z.output<typeof leadSchema>;

/** GET /leads/{id} and POST /leads: `{ data: Lead }`. */
export const leadResponseSchema = z.object({ data: leadSchema }).transform(({ data }) => data);

export type LeadResponseWire = z.input<typeof leadResponseSchema>;

export type LeadPage = CursorPage<Lead>;

/**
 * GET /leads: `{ data: Lead[], meta: PageMeta }`, read one lead at a time. A lead the
 * backend sends wrong is left out and counted rather than failing the whole page — see
 * `cursorPageSchema`. A page where no lead matches is still a contract violation.
 */
export const leadPageSchema = cursorPageSchema(leadSchema);

/** The backend's JSON for one page, as the mock backend must produce it. */
export type LeadPageWire = { data: LeadWire[]; meta: PageMetaWire };

// ── timeline and notes (LEAD-005, LEAD-006) ───────────────────────────────────

/** The backend's limit on a note (`LeadNote.note`, 1–2,000 characters after trimming). */
export const LEAD_NOTE_MAX_LENGTH = 2000;

/** The backend allows up to 100 events a page; 20 keeps the first paint short. */
export const TIMELINE_PAGE_SIZE = 20;

/**
 * One timeline entry. `kind` stays an open string (`lead.created`, `quotation.sent`, …) so
 * an event the backend adds later still shows; `payload` is read per kind by
 * `lib/timeline-entries.ts`. `actor` is null when unknown or hidden from a partner, and
 * its name can be empty, so it is read leniently rather than dropping the event.
 */
const timelineEventWireSchema = z.object({
  id: z.string().min(1),
  kind: z.string().min(1),
  occurred_at: isoDateTime,
  actor: z.object({ id: z.string().min(1), full_name: z.string() }).nullish(),
  payload: z.record(z.string(), z.unknown()).optional(),
});

export type TimelineEventWire = z.input<typeof timelineEventWireSchema>;

export const timelineEventSchema = timelineEventWireSchema.transform((wire) => ({
  id: wire.id,
  kind: wire.kind,
  occurredAt: wire.occurred_at,
  actor: wire.actor ? { id: wire.actor.id, name: wire.actor.full_name.trim() || null } : null,
  payload: wire.payload ?? {},
}));

export type TimelineEvent = z.output<typeof timelineEventSchema>;

/** GET /leads/{id}/timeline — newest first, read one event at a time (`cursorPageSchema`). */
export const timelinePageSchema = cursorPageSchema(timelineEventSchema);

export type TimelinePage = CursorPage<TimelineEvent>;

/** The backend's JSON for one timeline page, as the mock backend must produce it. */
export type TimelinePageWire = { data: TimelineEventWire[]; meta: PageMetaWire };

/** POST /leads/{id}/notes answers `{ data: TimelineEvent }`. */
export const timelineEventResponseSchema = z
  .object({ data: timelineEventSchema })
  .transform(({ data }) => data);

/** POST /leads/{id}/notes request body. */
export const addLeadNoteRequestSchema = z.object({
  note: z.string().trim().min(1).max(LEAD_NOTE_MAX_LENGTH),
});

export type AddLeadNoteRequest = z.infer<typeof addLeadNoteRequestSchema>;

const countSchema = z.number().int().nonnegative();

/**
 * LEAD-004 · GET /leads/stats — counts over the caller's scope, with the list's default
 * filter (merged leads left out). A bare object, not `{ data }`, and never capped.
 * Stage keys stay open strings so a stage the backend adds never hides the counts.
 */
export const leadStatsSchema = z
  .object({
    total: countSchema,
    by_stage: z.record(z.string(), countSchema),
    by_priority: z.record(z.enum(LEAD_PRIORITIES), countSchema),
    unassigned: countSchema,
  })
  .transform((wire) => ({
    total: wire.total,
    byStage: wire.by_stage,
    byPriority: wire.by_priority,
    unassigned: wire.unassigned,
  }));

export type LeadStats = z.output<typeof leadStatsSchema>;

/** The backend's JSON for the stats, as the mock backend must produce it. */
export type LeadStatsWire = z.input<typeof leadStatsSchema>;

/**
 * Sort columns. TODO(LEAD-001): the backend lists newest first and does not sort yet — the
 * `sort` and `order` parameters are our request to the backend (Docs/Frontend-Scope.md §10).
 */
export const LEAD_SORT_FIELDS = ["createdAt", "customerName", "estimatedValue"] as const;
export type LeadSortField = (typeof LEAD_SORT_FIELDS)[number];

/** The backend's name for each sort field, sent as `?sort=`. */
export const LEAD_SORT_WIRE_FIELDS: Readonly<Record<LeadSortField, string>> = {
  createdAt: "created_at",
  customerName: "farmer_name",
  estimatedValue: "estimated_value",
};

export const SORT_ORDERS = ["asc", "desc"] as const;
export type SortOrder = (typeof SORT_ORDERS)[number];

/** The backend allows up to 100 rows a page. */
export const LEAD_PAGE_SIZES = [25, 50, 100] as const;

export interface LeadListParams {
  /** From the previous page's `nextCursor`; null for the first page. */
  readonly cursor: string | null;
  readonly pageSize: number;
  readonly sort: LeadSortField;
  readonly order: SortOrder;
  /** Name, mobile or inquiry number. Already trimmed; empty means no search. */
  readonly q: string;
  /** Empty means the backend's default: every stage except merged. */
  readonly stage: readonly LeadStage[];
  /** A lead-source code from GET /lookups/lead-sources. The backend takes one. */
  readonly source: string | null;
  readonly type: LeadInquiryType | null;
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const INDIAN_MOBILE_E164 = /^\+91[6-9]\d{9}$/;
/** Whole rupees or rupees and paise, no grouping: "125000", "125000.50". */
const AMOUNT_PATTERN = /^\d{1,10}(\.\d{1,2})?$/;

/** POST /leads request body (`LeadCreate`) — what the backend receives. */
export const createLeadRequestSchema = z.object({
  farmer_name: z.string().min(1).max(200),
  mobile: z.string().regex(INDIAN_MOBILE_E164),
  email: z.email().max(254).nullable(),
  /** From GET /lookups/territories. The backend routes the lead to an office from it. */
  territory_id: z.string().regex(UUID_PATTERN),
  village: z.string().min(1).max(200).nullable(),
  inquiry_type: z.enum(LEAD_INQUIRY_TYPES),
  mis_system: z.string().min(1),
  /** Null lets the backend decide from who is asking: employee for staff, dealer for partners. */
  source: z.string().min(1).nullable(),
  estimated_value: z.string().regex(AMOUNT_PATTERN).nullable(),
  /** Becomes the first entry on the lead's timeline. */
  note: z.string().min(1).max(2000).nullable(),
});

export type CreateLeadRequest = z.infer<typeof createLeadRequestSchema>;

/** Empty optional text is "not set": the backend stores null, not "". */
function emptyToNull(value: string): string | null {
  return value === "" ? null : value;
}

/** The territory a form keeps: enough to send its id and to name it in the field. */
const territoryChoiceSchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    level: z.string().min(1),
    parent: z.object({ name: z.string() }).nullish(),
  })
  .nullable()
  .transform((territory, ctx) => {
    if (territory === null) {
      ctx.addIssue({ code: "custom", message: "Choose where the farmer is." });
      return z.NEVER;
    }
    return territory;
  });

/**
 * The New lead form: what people type → the request body. Error messages are user-facing
 * copy. Limits mirror `LeadCreate`, so the backend refuses nothing the form accepted.
 */
export const createLeadFormSchema = z
  .object({
    customerName: z
      .string()
      .trim()
      .min(1, "Enter the farmer's name.")
      .max(200, "Keep the name under 200 characters."),
    phone: z
      .string()
      .trim()
      .refine(
        (value) => normalizeIndianMobile(value) !== null,
        "Enter a 10-digit Indian mobile number.",
      )
      .transform((value) => normalizeIndianMobile(value) ?? value),
    email: z
      .string()
      .trim()
      .max(254, "Keep the email under 254 characters.")
      .refine(
        (value) => value === "" || z.email().safeParse(value).success,
        "Enter an email like name@example.com, or leave it empty.",
      )
      .transform(emptyToNull),
    territory: territoryChoiceSchema,
    village: z
      .string()
      .trim()
      .max(200, "Keep the village under 200 characters.")
      .transform(emptyToNull),
    type: z.enum(LEAD_INQUIRY_TYPES, "Choose the inquiry type."),
    misSystem: z.string("Choose the irrigation system.").min(1, "Choose the irrigation system."),
    source: z.string().nullish(),
    estimatedValue: z
      .string()
      .trim()
      .refine(
        (value) => value === "" || AMOUNT_PATTERN.test(value),
        "Enter an amount in rupees, e.g. 125000.",
      )
      .transform(emptyToNull),
    note: z
      .string()
      .trim()
      .max(2000, "Keep the note under 2,000 characters.")
      .transform(emptyToNull),
  })
  .transform((values): CreateLeadRequest => ({
    farmer_name: values.customerName,
    mobile: values.phone,
    email: values.email,
    territory_id: values.territory.id,
    village: values.village,
    inquiry_type: values.type,
    mis_system: values.misSystem,
    source: values.source ?? null,
    estimated_value: values.estimatedValue,
    note: values.note,
  }));

export type CreateLeadFormValues = z.input<typeof createLeadFormSchema>;
export type CreateLeadFormField = keyof CreateLeadFormValues;
