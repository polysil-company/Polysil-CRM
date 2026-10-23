import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  PARTNER_TYPES,
  type GstinLookupWire,
  type PartnerPageWire,
  type PartnerType,
  type PartnerWire,
} from "@/features/partners/api/partners.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can, type PermissionAction } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { normalizeIndianMobile } from "@/lib/format";
import { mockSessionPartnerId, partnerRecordInScope } from "@/mocks/data/partner-scope";
import type { MockPartnerRecord } from "@/mocks/data/partners";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { findMockTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse, mockWorkbook } from "./shared";

/**
 * CHNL-001…004 · Channel partners, with the backend's rules (`partners.md`, `services/masters.py`):
 *  - a distributor sits at the top; a dealer under a distributor, a sub-dealer under a dealer;
 *  - the code is unique across every partner, any case;
 *  - a GST-registered partner needs its GSTIN; GSTIN, PAN and mobile are checked for shape;
 *  - credit terms are shown to and set by staff who may edit partners;
 *  - closing deactivates every user anchored on the partner; reopening restores the partner
 *    only and says how many of its people stay inactive.
 */

const GSTIN_PATTERN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const PAN_PATTERN = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
const WRONG_TYPE = "wrong type for this parent: the order is distributor > dealer > sub_dealer";

function allowed(action: PermissionAction): boolean {
  return can(mockPermissionsFor(readMockRole()), "partners", action);
}

function staffCaller(): boolean {
  return !isPartnerRole(readMockRole());
}

function forbidden(): Response {
  return errorResponse(403, "insufficient_permission", "You may not do this.");
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function notFound(): Response {
  return errorResponse(404, "not_found", "No such partner.");
}

function needsKey(request: Request): Response | null {
  return request.headers.get("idempotency-key") === null
    ? errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.")
    : null;
}

/** A partner in the caller's scope: staff any, a partner user its own subtree (else a 404). */
function find(partnerId: unknown): MockPartnerRecord | undefined {
  const partner = mockDb.partners.find((item) => item.id === String(partnerId));
  return partner !== undefined && partnerRecordInScope(partner, mockDb.partners)
    ? partner
    : undefined;
}

function anchored(partnerId: string): { active: number; inactive: number } {
  const people = mockDb.users.filter(
    (user) => user.deleted_at === null && user.partner?.id === partnerId,
  );
  const active = people.filter((user) => user.is_active).length;
  return { active, inactive: people.length - active };
}

/** The partner as the API sends it: users counted now, credit terms for an editor only. */
function toWire(partner: MockPartnerRecord): PartnerWire {
  const editor = allowed("edit");
  const { parent_id: _parentId, ...wire } = partner;
  return {
    ...wire,
    credit_limit: editor ? partner.credit_limit : null,
    payment_terms_days: editor ? partner.payment_terms_days : null,
    users: anchored(partner.id).active,
  };
}

function filtered(url: URL): MockPartnerRecord[] {
  const params = url.searchParams;
  const q = (params.get("q") ?? "").trim().toLowerCase();
  const type = params.get("partner_type");
  const parentId = params.get("parent_id");
  const active = params.get("is_active");
  return mockDb.partners.filter(
    (partner) =>
      partnerRecordInScope(partner, mockDb.partners) &&
      (q === "" ||
        partner.name.toLowerCase().includes(q) ||
        partner.code.toLowerCase().includes(q) ||
        (partner.contact_name ?? "").toLowerCase().includes(q)) &&
      (type === null || partner.partner_type === type) &&
      (parentId === null || partner.parent_id === parentId) &&
      (active === null || String(partner.is_active) === active),
  );
}

function territoryRef(territoryId: string): MockPartnerRecord["territory"] | undefined {
  const territory = findMockTerritory(territoryId);
  return territory === undefined
    ? undefined
    : { id: territory.id, name: territory.name, level: territory.level };
}

const optionalText = z.string().nullish();

const createSchema = z.object({
  parent_id: z.string().nullish(),
  partner_type: z.enum(PARTNER_TYPES),
  code: z.string().trim().min(1, "Field required").max(32, "1 to 32 characters"),
  name: z.string().trim().min(1, "Field required").max(200, "1 to 200 characters"),
  territory_id: z.string().min(1, "Field required"),
  contact_name: optionalText,
  mobile: optionalText,
  email: optionalText,
  address: optionalText,
  gstin: optionalText,
  pan: optionalText,
  is_gst_registered: z.boolean().default(false),
  credit_limit: z.union([z.string(), z.number()]).nullish(),
  payment_terms_days: z.number().int().min(0).max(365).nullish(),
});

const patchSchema = z.object({
  name: z.string().trim().min(1).max(200).nullish(),
  contact_name: optionalText,
  mobile: optionalText,
  email: optionalText,
  address: optionalText,
  gstin: optionalText,
  pan: optionalText,
  is_gst_registered: z.boolean().nullish(),
  territory_id: z.string().nullish(),
  credit_limit: z.union([z.string(), z.number()]).nullish(),
  payment_terms_days: z.number().int().min(0).max(365).nullish(),
});

function fieldsOf(error: z.ZodError): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const issue of error.issues)
    fields[issue.path.map(String).join(".") || "body"] = issue.message;
  return fields;
}

/** The shapes the backend checks, each to its field; null clears, undefined leaves it. */
function contactFields(
  body: {
    mobile?: string | null | undefined;
    email?: string | null | undefined;
    gstin?: string | null | undefined;
    pan?: string | null | undefined;
    credit_limit?: string | number | null | undefined;
  },
  fields: Record<string, string>,
): {
  mobile: string | null | undefined;
  email: string | null | undefined;
  gstin: string | null | undefined;
  pan: string | null | undefined;
  credit: string | null | undefined;
} {
  const blank = (value: string | null | undefined): string | null | undefined =>
    value === undefined ? undefined : value === null || value.trim() === "" ? null : value.trim();
  const mobileText = blank(body.mobile);
  const mobile =
    mobileText === undefined || mobileText === null
      ? mobileText
      : (normalizeIndianMobile(mobileText)?.slice(1) ?? null);
  if (mobileText !== undefined && mobileText !== null && mobile === null) {
    fields.mobile = "not an Indian mobile";
  }
  // Null clears and undefined leaves the field, so each case is kept apart.
  const recase = (
    value: string | null | undefined,
    change: (text: string) => string,
  ): string | null | undefined => (value === undefined || value === null ? value : change(value));
  const email = recase(blank(body.email), (text) => text.toLowerCase());
  if (email !== undefined && email !== null && !z.email().safeParse(email).success) {
    fields.email = "not an email address";
  }
  const gstin = recase(blank(body.gstin), (text) => text.toUpperCase());
  if (gstin !== undefined && gstin !== null && !GSTIN_PATTERN.test(gstin)) {
    fields.gstin = "not a GSTIN";
  }
  const pan = recase(blank(body.pan), (text) => text.toUpperCase());
  if (pan !== undefined && pan !== null && !PAN_PATTERN.test(pan)) fields.pan = "not a PAN";
  const creditRaw =
    body.credit_limit === undefined || body.credit_limit === null
      ? body.credit_limit
      : String(body.credit_limit);
  let credit: string | null | undefined = creditRaw;
  if (creditRaw !== undefined && creditRaw !== null) {
    if (!/^\d+(\.\d{1,2})?$/.test(creditRaw)) fields.credit_limit = "rupees, 0 or more";
    else credit = Number(creditRaw).toFixed(2);
  }
  return { mobile, email, gstin, pan, credit };
}

function parentProblem(
  type: PartnerType,
  parentId: string | null | undefined,
): Record<string, string> | null {
  if (parentId === null || parentId === undefined) {
    // The backend's own rule: the order is distributor > dealer > sub_dealer.
    return type === "distributor" ? null : { partner_type: WRONG_TYPE };
  }
  const parent = find(parentId);
  if (parent === undefined || !parent.is_active) return { parent_id: "not found or closed" };
  const expected = PARTNER_TYPES[PARTNER_TYPES.indexOf(parent.partner_type) + 1];
  return expected === type ? null : { partner_type: WRONG_TYPE };
}

function newPartnerId(): string {
  return mockUuid(MOCK_ID_SPACE.partner, 1000 + mockDb.partners.length);
}

/** CHNL-005 · Adds a checked partner row, as the import commit does. */
export function addMockPartner(record: Omit<MockPartnerRecord, "id" | "created_at">): string {
  const id = newPartnerId();
  mockDb.partners.unshift({ ...record, id, created_at: new Date().toISOString() });
  return id;
}

const base = (rest = ""): string => buildApiUrl(`/partners${rest}`);

/**
 * CHNL-006 · The GST records the mock "finds" (FS-053). Any other well-formed GSTIN answers
 * `unavailable`, as the backend does until it has a GST data provider key (GAP-292).
 */
const MOCK_GST_RECORDS: Readonly<
  Record<string, { legal_name: string; trade_name: string | null; address: string }>
> = {
  "24AAACP1234F1Z5": {
    legal_name: "Patel Agro Irrigation Private Limited",
    trade_name: "Patel Agro",
    address: "Plot 14, GIDC Estate, Anand, Gujarat 388001",
  },
  "09AABCK5678M1Z2": {
    legal_name: "Kisan Jal Sinchai LLP",
    trade_name: null,
    address: "Station Road, Bareilly, Uttar Pradesh 243001",
  },
};

export function gstinLookup(gstin: string): GstinLookupWire["data"] {
  const shape = GSTIN_PATTERN.test(gstin);
  const base = {
    gstin,
    valid: shape,
    reason: shape ? null : "A GSTIN is 15 characters, like 24ABCDE1234F1Z5.",
    state_code: shape ? gstin.slice(0, 2) : null,
    pan: shape ? gstin.slice(2, 12) : null,
  };
  const record = MOCK_GST_RECORDS[gstin];
  if (!shape) return { ...base, lookup: "unavailable" };
  if (record === undefined) return { ...base, lookup: "unavailable" };
  return { ...base, lookup: "found", ...record, status: "Active" };
}

export const partnerHandlers = [
  http.get(buildApiUrl("/gstin/:gstin"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!staffCaller() || !allowed("view")) return forbidden();

    const body: GstinLookupWire = { data: gstinLookup(String(params.gstin).toUpperCase()) };
    return HttpResponse.json(body);
  }),

  http.get(base(), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? "25");
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const rows = scenario === "empty" ? [] : filtered(url);
    const page = rows.slice(offset, offset + limit);
    const next = offset + limit < rows.length ? encodeCursor(offset + limit) : null;
    const body: PartnerPageWire = {
      data: page.map(toWire),
      meta: {
        limit,
        ...(next === null ? {} : { next_cursor: next }),
        ...(url.searchParams.get("include_total") === "true" ? { total: rows.length } : {}),
      },
    };
    return HttpResponse.json(body);
  }),

  /** Before /partners/:partnerId. */
  http.get(base("/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const rows = filtered(new URL(request.url));
    if (rows.length > 5000) {
      return errorResponse(422, "export_too_large", "More than 5,000 rows: narrow the filters.");
    }
    return mockWorkbook(
      "partners",
      ["Code", "Name", "Type", "Under", "Territory", "Contact", "Mobile", "GSTIN", "Open"],
      rows.map((partner) => [
        partner.code,
        partner.name,
        partner.partner_type,
        partner.parent?.name ?? "",
        partner.territory?.name ?? "",
        partner.contact_name ?? "",
        partner.mobile ?? "",
        partner.gstin ?? "",
        partner.is_active ? "yes" : "no",
      ]),
    );
  }),

  http.get(base("/:partnerId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const partner = find(params.partnerId);
    if (partner === undefined) return notFound();
    return HttpResponse.json({ data: toWire(partner) });
  }),

  http.post(base(), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("create")) return forbidden();
    const missingKey = needsKey(request);
    if (missingKey) return missingKey;
    const key = request.headers.get("idempotency-key") ?? "";
    const raw = await request.text();
    const replay = mockDb.partnerWrites.get(key);
    if (replay !== undefined) {
      if (replay.body !== raw) {
        return errorResponse(409, "idempotency_conflict", "The key was used for another body.");
      }
      const made = find(replay.partnerId);
      if (made !== undefined) return HttpResponse.json({ data: toWire(made) }, { status: 201 });
    }
    const parsed = createSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const fields: Record<string, string> = {};
    if (!staffCaller() && (body.credit_limit != null || body.payment_terms_days != null)) {
      fields[body.credit_limit == null ? "payment_terms_days" : "credit_limit"] =
        "set by staff only";
    }
    Object.assign(fields, parentProblem(body.partner_type, body.parent_id));
    // CHNL-002 · a distributor or dealer on the portal adds the next type down under itself.
    const mine = mockSessionPartnerId();
    if (mine !== null && body.parent_id !== mine) {
      fields.parent_id = "a partner adds partners under itself only";
    }
    const territory = territoryRef(body.territory_id);
    if (territory === undefined) fields.territory_id = "not found";
    const shaped = contactFields(body, fields);
    if (body.is_gst_registered && (shaped.gstin ?? null) === null && fields.gstin === undefined) {
      fields.gstin = "required when GST registered";
    }
    if (
      mockDb.partners.some(
        (partner) => partner.code.toLowerCase() === body.code.trim().toLowerCase(),
      )
    ) {
      fields.code = "already in use";
    }
    if (Object.keys(fields).length > 0) return invalid(fields);
    const parent = body.parent_id == null ? undefined : find(body.parent_id);
    const id = addMockPartner({
      code: body.code.trim(),
      name: body.name.trim(),
      partner_type: body.partner_type,
      price_tier: body.partner_type,
      parent_id: parent?.id ?? null,
      parent:
        parent === undefined
          ? null
          : { id: parent.id, name: parent.name, partner_type: parent.partner_type },
      territory: territory ?? null,
      contact_name: body.contact_name?.trim() || null,
      mobile: shaped.mobile ?? null,
      email: shaped.email ?? null,
      address: body.address?.trim() || null,
      gstin: shaped.gstin ?? null,
      pan: shaped.pan ?? null,
      is_gst_registered: body.is_gst_registered,
      credit_limit: shaped.credit ?? null,
      payment_terms_days: body.payment_terms_days ?? null,
      is_active: true,
    });
    mockDb.partnerWrites.set(key, { body: raw, partnerId: id });
    const made = find(id);
    return made === undefined
      ? notFound()
      : HttpResponse.json({ data: toWire(made) }, { status: 201 });
  }),

  http.patch(base("/:partnerId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const missingKey = needsKey(request);
    if (missingKey) return missingKey;
    const partner = find(params.partnerId);
    if (partner === undefined) return notFound();
    const json: unknown = await request.json();
    const parsed = patchSchema.safeParse(json);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const sent = Object.keys(typeof json === "object" && json !== null ? json : {});
    if (sent.length === 0) return invalid({ body: "nothing to change" });
    const fields: Record<string, string> = {};
    if (!staffCaller()) {
      for (const field of ["territory_id", "credit_limit", "payment_terms_days"] as const) {
        if (sent.includes(field)) fields[field] = "a partner may edit its contact details only";
      }
    }
    if (sent.includes("name") && (body.name ?? null) === null) fields.name = "cannot be cleared";
    if (sent.includes("territory_id") && (body.territory_id ?? null) === null) {
      fields.territory_id = "cannot be cleared";
    }
    const territory =
      body.territory_id === undefined || body.territory_id === null
        ? undefined
        : territoryRef(body.territory_id);
    if (body.territory_id != null && territory === undefined) fields.territory_id = "not found";
    const shaped = contactFields(body, fields);
    const gstRegistered = body.is_gst_registered ?? partner.is_gst_registered;
    const gstin = shaped.gstin === undefined ? partner.gstin : shaped.gstin;
    if (gstRegistered && gstin === null && fields.gstin === undefined) {
      fields.gstin = "required when GST registered";
    }
    if (Object.keys(fields).length > 0) return invalid(fields);
    const next: MockPartnerRecord = {
      ...partner,
      ...(body.name == null ? {} : { name: body.name.trim() }),
      ...(sent.includes("contact_name") ? { contact_name: body.contact_name?.trim() || null } : {}),
      ...(shaped.mobile === undefined ? {} : { mobile: shaped.mobile }),
      ...(shaped.email === undefined ? {} : { email: shaped.email }),
      ...(sent.includes("address") ? { address: body.address?.trim() || null } : {}),
      gstin,
      ...(shaped.pan === undefined ? {} : { pan: shaped.pan }),
      is_gst_registered: gstRegistered,
      ...(territory === undefined ? {} : { territory }),
      ...(shaped.credit === undefined ? {} : { credit_limit: shaped.credit }),
      ...(body.payment_terms_days === undefined
        ? {}
        : { payment_terms_days: body.payment_terms_days }),
    };
    mockDb.partners = mockDb.partners.map((item) => {
      if (item.id === partner.id) return next;
      // A renamed parent is renamed on the partners under it.
      return item.parent_id === partner.id && item.parent !== null
        ? { ...item, parent: { ...item.parent, name: next.name } }
        : item;
    });
    return HttpResponse.json({ data: toWire(next) });
  }),

  ...(["close", "reopen"] as const).map((action) =>
    http.post(base(`/:partnerId/${action}`), async ({ params, request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!allowed("edit") || !staffCaller()) return forbidden();
      const missingKey = needsKey(request);
      if (missingKey) return missingKey;
      const partner = find(params.partnerId);
      if (partner === undefined) return notFound();
      if (action === "close" && partner.is_active) {
        // Every user anchored here is signed out and deactivated.
        mockDb.users = mockDb.users.map((user) =>
          user.partner?.id === partner.id && user.deleted_at === null
            ? { ...user, is_active: false, active_sessions: 0 }
            : user,
        );
      }
      partner.is_active = action === "reopen";
      return HttpResponse.json({
        data: { ...toWire(partner), users_inactive: anchored(partner.id).inactive },
      });
    }),
  ),
];
