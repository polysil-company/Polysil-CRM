import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  DEALER_APPLICATION_STATUSES,
  FIRM_TYPES,
  OPEN_STATUSES,
  type DealerApplicationWire,
} from "@/features/dealer-applications/api/dealer-applications.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { normalizeIndianMobile } from "@/lib/format";
import type { MockDealerApplication } from "@/mocks/data/dealer-applications";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, MOCK_STAFF, mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { findMockTerritory, MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { addMockPartner, gstinLookup } from "./partners";
import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * CHNL-007 · Dealer applications for the mock backend, following `dealer_applications.py`:
 *  - staff who see partners start, read, fill, submit, withdraw and renew;
 *  - a State Manager or above (or Admin), never whoever started it, decides a submitted one;
 *  - `missing` names the fields and documents still needed; submitting needs none missing;
 *  - the link (`apply_url`) is in the answer only after creating it or renewing it.
 */

const GSTIN_PATTERN = /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const PAN_PATTERN = /^[A-Z]{5}\d{4}[A-Z]$/;
const IFSC_PATTERN = /^[A-Z]{4}0[A-Z0-9]{6}$/;
const LINK_DAYS = 30;
/** The roles that decide, besides Admin: State Manager or above (role level 3+). */
const DECIDERS = new Set(["state_manager", "regional_manager", "admin"]);

const DAY = 24 * 60 * 60 * 1000;

function caller(): { id: string; full_name: string } {
  const me = mockMeFor(readMockRole()).data;
  return { id: me.id, full_name: me.full_name };
}

function seesPartners(): boolean {
  const role = readMockRole();
  return !isPartnerRole(role) && can(mockPermissionsFor(role), "partners", "view");
}

function forbidden(): Response {
  return errorResponse(
    403,
    "insufficient_permission",
    "Dealer applications are for staff who see partners.",
  );
}

function notFound(): Response {
  return errorResponse(404, "not_found", "No such application.");
}

function closed(): Response {
  return errorResponse(409, "application_closed", "This application is closed to changes.");
}

function invalid(fields: Record<string, string>, code = "validation_error"): Response {
  return errorResponse(422, code, "Some fields need correcting.", fields);
}

/** Where the applicant fills it in: this app's own `/dealer-apply/<token>` page. */
function applyUrl(token: string): string {
  const origin = typeof window === "undefined" ? "http://localhost:3000" : window.location.origin;
  return `${origin}/dealer-apply/${token}`;
}

function newToken(): string {
  return `apply-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
}

function documentsOf(applicationId: string): Set<string> {
  return new Set(
    mockDb.documents
      .filter(
        (document) =>
          !document.removed &&
          document.record_type === "dealer_application" &&
          document.record_id === applicationId,
      )
      .map((document) => document.doc_type),
  );
}

/** The backend's `dealer_application_missing`: fields first, then the three documents. */
export function missingOf(application: MockDealerApplication): string[] {
  const docs = documentsOf(application.id);
  const missing = [
    application.firm_type === null ? "firm_type" : null,
    application.gst_registered && application.gstin === null ? "gstin" : null,
    application.pan === null ? "pan" : null,
    application.address === null ? "address" : null,
    application.pincode === null ? "pincode" : null,
    application.bank_account_name === null ? "bank_account_name" : null,
    application.bank_account_no === null ? "bank_account_no" : null,
    application.bank_ifsc === null ? "bank_ifsc" : null,
    application.gst_registered && !docs.has("gst_certificate") ? "gst_certificate" : null,
    docs.has("pan_card") ? null : "pan_card",
    docs.has("cancelled_cheque") ? null : "cancelled_cheque",
  ];
  return missing.filter((item) => item !== null).sort();
}

function mayDecide(application: MockDealerApplication): boolean {
  return (
    application.status === "submitted" &&
    DECIDERS.has(readMockRole()) &&
    application.created_by?.id !== caller().id
  );
}

/** The application as the API sends it, with what is missing and what the reader may do. */
export function dealerApplicationWire(
  application: MockDealerApplication,
  withLink = false,
): DealerApplicationWire {
  const { token, ...stored } = application;
  const open = OPEN_STATUSES.some((status) => status === application.status);
  const decide = mayDecide(application);
  const seesBank = decide || can(mockPermissionsFor(readMockRole()), "partners", "edit");
  const account = application.bank_account_no;
  return {
    ...stored,
    bank_account_no: account === null || seesBank ? account : `XXXX${account.slice(-4)}`,
    missing: missingOf(application),
    apply_url: withLink ? applyUrl(token) : null,
    can: {
      edit: open,
      decide,
      withdraw: open,
      renew: application.status === "draft" || application.status === "returned",
    },
  };
}

function blankApplication(input: {
  firm: string;
  contact: string;
  mobile: string;
  territory: { id: string; name: string };
  leadId: string | null;
  by: { id: string; full_name: string } | null;
  createdAt: string;
  serial: number;
}): MockDealerApplication {
  return {
    id: mockUuid(MOCK_ID_SPACE.dealerApplication, input.serial),
    token: newToken(),
    status: "draft",
    firm_name: input.firm,
    contact_name: input.contact,
    mobile: input.mobile,
    territory: input.territory,
    lead_id: input.leadId,
    firm_type: null,
    gst_registered: true,
    gstin: null,
    pan: null,
    address: null,
    pincode: null,
    email: null,
    godown_address: null,
    years_in_business: null,
    current_brands: null,
    notes: null,
    bank_account_name: null,
    bank_account_no: null,
    bank_ifsc: null,
    gst_lookup: null,
    gst_state_mismatch: false,
    partner_id: null,
    user_id: null,
    decided_by: null,
    decided_at: null,
    decision_remark: null,
    link_expires_at: new Date(Date.parse(input.createdAt) + LINK_DAYS * DAY).toISOString(),
    created_by: input.by,
    created_at: input.createdAt,
    submitted_at: null,
  };
}

/** Replays: the same Idempotency-Key and body answer the first response again. */
const replays = new Map<string, { body: string; response: () => Response }>();

/** A few applications at different steps, started by a colleague so a manager may decide. */
export function mockDealerApplications(): MockDealerApplication[] {
  if (mockDb.dealerApplications !== null) return mockDb.dealerApplications;
  replays.clear();
  const districts = MOCK_TERRITORIES.filter((territory) => territory.level === "district");
  const by = MOCK_STAFF[1] ?? null;
  const now = Date.now();
  const at = (days: number): string => new Date(now - days * DAY).toISOString();
  const place = (index: number): { id: string; name: string } => {
    const district = districts[index % Math.max(districts.length, 1)];
    return district === undefined
      ? { id: "unknown", name: "Unknown" }
      : { id: district.id, name: district.name };
  };
  const complete = {
    firm_type: "proprietorship",
    gst_registered: true,
    pan: "AAACP1234F",
    address: "Shop 4, Market Yard, Rajkot",
    pincode: "360001",
    bank_account_name: "Patel Agro",
    bank_account_no: "001234567890",
    bank_ifsc: "SBIN0001234",
  } as const;
  const rows: MockDealerApplication[] = [
    {
      ...blankApplication({
        firm: "Shree Krishna Krishi Kendra",
        contact: "Mahesh Bhalala",
        mobile: "919824012345",
        territory: place(0),
        leadId: null,
        by,
        createdAt: at(2),
        serial: 1,
      }),
    },
    {
      ...blankApplication({
        firm: "Patel Agro",
        contact: "Jignesh Patel",
        mobile: "919825098765",
        territory: place(1),
        leadId: null,
        by,
        createdAt: at(6),
        serial: 2,
      }),
      ...complete,
      gstin: "24AAACP1234F1Z5",
      gst_lookup: {
        valid: true,
        lookup: "found",
        legal_name: "Patel Agro Irrigation Private Limited",
        trade_name: "Patel Agro",
      },
      years_in_business: 8,
      current_brands: "Jain, Netafim",
      status: "submitted",
      submitted_at: at(1),
    },
    {
      ...blankApplication({
        firm: "Umiya Irrigation",
        contact: "Ketan Ghodasara",
        mobile: "919879011122",
        territory: place(2),
        leadId: null,
        by,
        createdAt: at(10),
        serial: 3,
      }),
      ...complete,
      gst_registered: false,
      pan: "BBBPU1234K",
      bank_account_name: "Umiya Irrigation",
      status: "returned",
      submitted_at: at(5),
      decided_by: MOCK_STAFF[3] ?? null,
      decided_at: at(4),
      decision_remark: "The cancelled cheque is unreadable. Upload a clearer photo.",
    },
  ];
  mockDb.dealerApplications = rows;
  // the submitted one has its documents, so it is complete
  const submitted = rows[1];
  if (submitted !== undefined) {
    for (const docType of ["gst_certificate", "pan_card", "cancelled_cheque"]) {
      mockDb.documents.push({
        id: mockUuid(MOCK_ID_SPACE.document, 900 + mockDb.documents.length),
        record_type: "dealer_application",
        record_id: submitted.id,
        record_label: null,
        doc_type: docType,
        doc_type_label: docType.replaceAll("_", " "),
        name: null,
        filename: `${docType}.pdf`,
        content_type: "application/pdf",
        size_bytes: 120_000,
        preview: true,
        uploaded_by: by,
        uploaded_at: at(2),
        fingerprint: `seed-${docType}`,
        removed: false,
      });
    }
  }
  return rows;
}

function find(applicationId: unknown): MockDealerApplication | undefined {
  return mockDealerApplications().find((item) => item.id === String(applicationId));
}

/**
 * LEAD-015 · Winning a dealership lead starts an application (FS-053), with the same
 * refusals as starting one by hand.
 */
export function startMockDealerApplicationFor(input: {
  firm: string;
  contact: string;
  mobile: string;
  territory: { id: string; name: string };
  leadId: string | null;
}): { application: MockDealerApplication } | { refused: "mobile_in_use" | "application_open" } {
  const rows = mockDealerApplications();
  if (
    mockDb.partners.some((partner) => partner.mobile === input.mobile) ||
    mockDb.users.some((user) => user.mobile === input.mobile)
  ) {
    return { refused: "mobile_in_use" };
  }
  if (
    rows.some(
      (row) => row.mobile === input.mobile && OPEN_STATUSES.some((status) => status === row.status),
    )
  ) {
    return { refused: "application_open" };
  }
  const application = blankApplication({
    ...input,
    by: caller(),
    createdAt: new Date().toISOString(),
    serial: 100 + rows.length,
  });
  rows.unshift(application);
  return { application };
}

const text = z.string().trim();
const nullableText = z
  .string()
  .trim()
  .nullable()
  .transform((value) => (value === "" ? null : value));

const createSchema = z.object({
  firm_name: text.min(1).max(200),
  contact_name: text.min(1).max(120),
  mobile: text.min(1),
  territory_id: text.min(1),
  lead_id: z.string().nullish(),
});

const fieldsSchema = z.object({
  firm_name: text.min(1).max(200).optional(),
  contact_name: text.min(1).max(120).optional(),
  firm_type: z.enum(FIRM_TYPES).nullable().optional(),
  gst_registered: z.boolean().optional(),
  gstin: nullableText.optional(),
  pan: nullableText.optional(),
  address: nullableText.optional(),
  pincode: nullableText.optional(),
  email: nullableText.optional(),
  godown_address: nullableText.optional(),
  years_in_business: z.number().int().min(0).max(200).nullable().optional(),
  current_brands: nullableText.optional(),
  notes: nullableText.optional(),
  bank_account_name: nullableText.optional(),
  bank_account_no: nullableText.optional(),
  bank_ifsc: nullableText.optional(),
});

const decisionSchema = z.object({
  decision: z.enum(["approve", "reject", "return"]),
  remark: z.string().trim().nullish(),
  parent_id: z.string().nullish(),
  code: z.string().trim().nullish(),
});

/** The fields written, upper-cased and checked as `_clean_fields` does. */
function applyFields(
  application: MockDealerApplication,
  body: z.infer<typeof fieldsSchema>,
): Record<string, string> | null {
  const fields: Record<string, string> = {};
  const upper = (value: string | null | undefined): string | null | undefined =>
    value === undefined || value === null ? value : value.toUpperCase();
  const gstin = upper(body.gstin);
  const pan = upper(body.pan);
  const ifsc = upper(body.bank_ifsc);
  if (gstin != null && !GSTIN_PATTERN.test(gstin)) fields.gstin = "not a GSTIN";
  if (pan != null && !PAN_PATTERN.test(pan)) fields.pan = "not a PAN";
  if (ifsc != null && !IFSC_PATTERN.test(ifsc)) fields.bank_ifsc = "not an IFSC";
  if (body.pincode != null && !/^\d{6}$/.test(body.pincode)) fields.pincode = "six digits";
  if (body.bank_account_no != null && !/^\d{9,18}$/.test(body.bank_account_no)) {
    fields.bank_account_no = "9 to 18 digits";
  }
  if (Object.keys(fields).length > 0) return fields;
  const nextGstin = gstin === undefined ? application.gstin : gstin;
  const nextPan = pan === undefined ? application.pan : pan;
  if (nextGstin !== null && nextPan !== null && nextGstin.slice(2, 12) !== nextPan) {
    return { pan: "not the PAN inside the GSTIN" };
  }
  const { gstin: _g, pan: _p, bank_ifsc: _i, ...rest } = body;
  for (const [key, value] of Object.entries(rest)) {
    if (value !== undefined) Object.assign(application, { [key]: value });
  }
  if (gstin !== undefined) {
    application.gstin = gstin;
    const lookup = gstin === null ? null : gstinLookup(gstin);
    application.gst_lookup =
      lookup === null
        ? null
        : {
            valid: lookup.valid,
            lookup: lookup.lookup,
            legal_name: lookup.legal_name ?? null,
            trade_name: lookup.trade_name ?? null,
          };
  }
  if (pan !== undefined) application.pan = pan;
  if (ifsc !== undefined) application.bank_ifsc = ifsc;
  return null;
}

function nextDealerCode(): string {
  const taken = mockDb.partners.filter((partner) => partner.code.startsWith("DLR-GJ-")).length;
  return `DLR-GJ-${String(taken + 1).padStart(4, "0")}`;
}

function replayOf(request: Request, raw: unknown): Response | null | "conflict" {
  const key = request.headers.get("idempotency-key");
  if (key === null)
    return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
  const seen = replays.get(key);
  if (seen === undefined) return null;
  return seen.body === JSON.stringify(raw) ? seen.response() : "conflict";
}

function remember(request: Request, raw: unknown, response: () => Response): Response {
  const key = request.headers.get("idempotency-key");
  if (key !== null) replays.set(key, { body: JSON.stringify(raw), response });
  return response();
}

async function bodyOf(request: Request): Promise<unknown> {
  const text = await request.text();
  if (text === "") return null;
  const parsed: unknown = JSON.parse(text);
  return parsed;
}

const base = (rest = ""): string => buildApiUrl(`/dealer-applications${rest}`);

export const dealerApplicationHandlers = [
  http.get(base(), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const url = new URL(request.url);
    const statuses = (url.searchParams.get("status") ?? "").split(",").filter(Boolean);
    if (statuses.some((status) => !DEALER_APPLICATION_STATUSES.some((item) => item === status))) {
      return invalid({ status: "not a status" });
    }
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const rows =
      scenario === "empty"
        ? []
        : mockDealerApplications().filter(
            (row) =>
              (statuses.length === 0 || statuses.includes(row.status)) &&
              (q === "" ||
                row.firm_name.toLowerCase().includes(q) ||
                row.contact_name.toLowerCase().includes(q) ||
                row.mobile.includes(q)),
          );
    return HttpResponse.json({
      data: rows.slice(0, 200).map((row) => ({
        id: row.id,
        status: row.status,
        firm_name: row.firm_name,
        contact_name: row.contact_name,
        territory_name: row.territory.name,
        created_at: row.created_at,
        submitted_at: row.submitted_at,
      })),
    });
  }),

  http.post(base(), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const raw = await bodyOf(request);
    const replay = replayOf(request, raw);
    if (replay === "conflict")
      return errorResponse(409, "idempotency_conflict", "Another request used that key.");
    if (replay !== null) return replay;
    const parsed = createSchema.safeParse(raw);
    if (!parsed.success) {
      const fields: Record<string, string> = {};
      for (const issue of parsed.error.issues) fields[String(issue.path[0])] = "required";
      return invalid(fields);
    }
    const body = parsed.data;
    const mobile = normalizeIndianMobile(body.mobile)?.replace(/^\+/, "") ?? null;
    if (mobile === null) return invalid({ mobile: "not an Indian mobile number" });
    const territory = findMockTerritory(body.territory_id);
    if (territory === undefined) return invalid({ territory_id: "outside your scope" });
    const started = startMockDealerApplicationFor({
      firm: body.firm_name,
      contact: body.contact_name,
      mobile,
      territory: { id: territory.id, name: territory.name },
      leadId: body.lead_id ?? null,
    });
    if ("refused" in started) {
      return started.refused === "mobile_in_use"
        ? errorResponse(409, "mobile_in_use", "This mobile already signs someone in.")
        : errorResponse(409, "application_open", "An open application already has this mobile.");
    }
    const wire = dealerApplicationWire(started.application, true);
    return remember(request, raw, () => HttpResponse.json({ data: wire }, { status: 201 }));
  }),

  http.get(base("/:applicationId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const application = find(params.applicationId);
    if (application === undefined) return notFound();
    return HttpResponse.json({ data: dealerApplicationWire(application) });
  }),

  http.patch(base("/:applicationId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const application = find(params.applicationId);
    if (application === undefined) return notFound();
    const raw = await bodyOf(request);
    const replay = replayOf(request, raw);
    if (replay === "conflict")
      return errorResponse(409, "idempotency_conflict", "Another request used that key.");
    if (replay !== null) return replay;
    if (!OPEN_STATUSES.some((status) => status === application.status)) return closed();
    const parsed = fieldsSchema.safeParse(raw);
    if (!parsed.success) {
      const fields: Record<string, string> = {};
      for (const issue of parsed.error.issues) fields[String(issue.path[0])] = issue.message;
      return invalid(fields);
    }
    const problems = applyFields(application, parsed.data);
    if (problems !== null) return invalid(problems);
    const wire = dealerApplicationWire(application);
    return remember(request, raw, () => HttpResponse.json({ data: wire }));
  }),

  http.post(base("/:applicationId/submit"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const application = find(params.applicationId);
    if (application === undefined) return notFound();
    const replay = replayOf(request, null);
    if (replay === "conflict")
      return errorResponse(409, "idempotency_conflict", "Another request used that key.");
    if (replay !== null) return replay;
    if (application.status !== "draft" && application.status !== "returned") return closed();
    const missing = missingOf(application);
    if (missing.length > 0) {
      return invalid(
        Object.fromEntries(missing.map((key) => [key, "required"])),
        "application_incomplete",
      );
    }
    application.status = "submitted";
    application.submitted_at = new Date().toISOString();
    const wire = dealerApplicationWire(application);
    return remember(request, null, () => HttpResponse.json({ data: wire }));
  }),

  http.post(base("/:applicationId/withdraw"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const application = find(params.applicationId);
    if (application === undefined) return notFound();
    const raw = await bodyOf(request);
    const replay = replayOf(request, raw);
    if (replay === "conflict")
      return errorResponse(409, "idempotency_conflict", "Another request used that key.");
    if (replay !== null) return replay;
    const parsed = z.object({ remark: z.string().trim().min(1).max(500) }).safeParse(raw);
    if (!parsed.success) return invalid({ remark: "required" });
    if (!OPEN_STATUSES.some((status) => status === application.status)) return closed();
    application.status = "withdrawn";
    application.decision_remark = parsed.data.remark;
    application.decided_by = caller();
    application.decided_at = new Date().toISOString();
    const wire = dealerApplicationWire(application);
    return remember(request, raw, () => HttpResponse.json({ data: wire }));
  }),

  http.post(base("/:applicationId/link"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const application = find(params.applicationId);
    if (application === undefined) return notFound();
    const replay = replayOf(request, null);
    if (replay === "conflict")
      return errorResponse(409, "idempotency_conflict", "Another request used that key.");
    if (replay !== null) return replay;
    if (application.status !== "draft" && application.status !== "returned") return closed();
    application.token = newToken();
    application.link_expires_at = new Date(Date.now() + LINK_DAYS * DAY).toISOString();
    const wire = dealerApplicationWire(application, true);
    return remember(request, null, () => HttpResponse.json({ data: wire }));
  }),

  http.post(base("/:applicationId/decision"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!seesPartners()) return forbidden();
    const application = find(params.applicationId);
    if (application === undefined) return notFound();
    const raw = await bodyOf(request);
    const replay = replayOf(request, raw);
    if (replay === "conflict")
      return errorResponse(409, "idempotency_conflict", "Another request used that key.");
    if (replay !== null) return replay;
    const parsed = decisionSchema.safeParse(raw);
    if (!parsed.success) return invalid({ decision: "approve, reject or return" });
    const body = parsed.data;
    if (application.status !== "submitted") {
      return OPEN_STATUSES.some((status) => status === application.status)
        ? closed()
        : errorResponse(409, "already_decided", "This application has already been decided.");
    }
    if (!mayDecide(application)) {
      return errorResponse(
        403,
        "insufficient_permission",
        "Only a State Manager or above, other than whoever started it, decides.",
      );
    }
    const remark = body.remark?.trim() || null;
    if (body.decision !== "approve" && remark === null) {
      return invalid({ remark: "required to reject or return" });
    }
    if (body.decision === "approve") {
      const parent =
        body.parent_id == null
          ? null
          : mockDb.partners.find(
              (partner) =>
                partner.id === body.parent_id &&
                partner.partner_type === "distributor" &&
                partner.is_active,
            );
      if (body.parent_id != null && (parent === undefined || parent === null)) {
        return invalid({ parent_id: "not an active distributor" });
      }
      const code = body.code?.trim() ? body.code.trim().toUpperCase() : nextDealerCode();
      if (mockDb.partners.some((partner) => partner.code === code)) {
        return errorResponse(409, "code_in_use", "That partner code is taken.");
      }
      application.partner_id = addMockPartner({
        code,
        name: application.firm_name,
        partner_type: "dealer",
        price_tier: "dealer",
        parent:
          parent == null ? null : { id: parent.id, name: parent.name, partner_type: "distributor" },
        parent_id: parent?.id ?? null,
        territory: { ...application.territory, level: "district" },
        contact_name: application.contact_name,
        mobile: application.mobile,
        email: application.email,
        address: application.address,
        gstin: application.gstin,
        pan: application.pan,
        is_gst_registered: application.gst_registered,
        credit_limit: null,
        payment_terms_days: null,
        is_active: true,
      });
      application.status = "approved";
    } else {
      application.status = body.decision === "return" ? "returned" : "rejected";
    }
    application.decision_remark = remark;
    application.decided_by = caller();
    application.decided_at = new Date().toISOString();
    const wire = dealerApplicationWire(application);
    return remember(request, raw, () => HttpResponse.json({ data: wire }));
  }),
];
