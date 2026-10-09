import { http, HttpResponse } from "msw";
import { z } from "zod";

import type {
  PublicLeadFormWire,
  QrCodeWire,
} from "@/features/lead-capture/api/lead-capture.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { readMockRole } from "@/lib/dev/mock-settings";
import { normalizeIndianMobile } from "@/lib/format";
import { mockEnquiryUrl, mockQrCode } from "@/mocks/data/lead-capture";
import { mockLookupRows } from "@/mocks/data/lookups";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, MOCK_PARTNERS, mockUuid } from "@/mocks/data/reference";
import { findMockTerritory, MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { createLeadFrom } from "./leads";
import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/** The code the mock treats as wrong, so a test can see `invalid_code`. Any other six digits match. */
export const MOCK_WRONG_ENQUIRY_CODE = "000000";

const EXPIRES_IN = 600;
const RESEND_AFTER = 60;

function may(action: "view" | "create" | "edit"): boolean {
  return mockPermissionsFor(readMockRole()).some(
    (permission) => permission.module === "leads" && permission.actions.includes(action),
  );
}

const qrBodySchema = z.object({
  label: z.string().trim().min(1).max(120),
  campaign: z.string().trim().max(120).nullish(),
  partner_id: z.string().min(1).nullish(),
  territory_id: z.string().min(1).nullish(),
});

const qrPatchSchema = qrBodySchema.partial().extend({ is_active: z.boolean().nullish() });

function partnerRef(partnerId: string): QrCodeWire["partner"] | undefined {
  const partner = MOCK_PARTNERS.find((item) => item.id === partnerId);
  return partner === undefined
    ? undefined
    : { id: partner.id, name: partner.name, partner_type: partner.partner_type };
}

function territoryRef(territoryId: string): QrCodeWire["territory"] | undefined {
  const territory = findMockTerritory(territoryId);
  return territory === undefined
    ? undefined
    : { id: territory.id, name: territory.name, level: territory.level };
}

const publicLeadSchema = z.object({
  mobile: z.string().min(10).max(20),
  code: z.string().regex(/^\d{6}$/),
  farmer_name: z.string().trim().min(1).max(200),
  territory_id: z.string().min(1),
  village: z.string().trim().max(120).nullish(),
  mis_system: z.string().min(1),
  inquiry_type: z.enum(["commercial", "subsidised", "industrial"]).default("commercial"),
  note: z.string().trim().max(1000).nullish(),
  qr: z.string().max(12).nullish(),
});

/**
 * LEAD-013 · The staff QR codes; LEAD-014 · the public enquiry page. The mock sends no
 * WhatsApp: any six digits match except `000000`, which stands for a wrong code.
 */
export const leadCaptureHandlers = [
  http.get(buildApiUrl("/lead-qr-codes"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!may("view")) return errorResponse(403, "forbidden", "You may not see leads.");
    const active = new URL(request.url).searchParams.get("active");
    const rows =
      scenario === "empty"
        ? []
        : mockDb.qrCodes.filter((row) => active === null || row.is_active === (active === "true"));
    return HttpResponse.json({ data: rows });
  }),

  http.post(buildApiUrl("/lead-qr-codes"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!may("create")) return errorResponse(403, "forbidden", "You may not make QR codes.");
    const parsed = qrBodySchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        label: "1 to 120 characters",
      });
    }
    const body = parsed.data;
    const partner = body.partner_id == null ? null : partnerRef(body.partner_id);
    if (partner === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        partner_id: "not found",
      });
    }
    const territory = body.territory_id == null ? null : territoryRef(body.territory_id);
    if (territory === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        territory_id: "not found",
      });
    }
    const serial = mockDb.qrCodes.length + 1;
    const code = mockQrCode(serial);
    const row: QrCodeWire = {
      id: mockUuid(MOCK_ID_SPACE.qrCode, serial),
      code,
      url: mockEnquiryUrl(code),
      label: body.label,
      campaign: body.campaign ?? null,
      partner,
      territory,
      is_active: true,
      lead_count: 0,
      created_at: new Date().toISOString(),
    };
    mockDb.qrCodes = [row, ...mockDb.qrCodes];
    return HttpResponse.json({ data: row }, { status: 201 });
  }),

  http.patch(buildApiUrl("/lead-qr-codes/:qrId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!may("edit")) return errorResponse(403, "forbidden", "You may not change QR codes.");
    const row = mockDb.qrCodes.find((item) => item.id === params.qrId);
    if (row === undefined) return errorResponse(404, "not_found", "Not yours.");
    const parsed = qrPatchSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        label: "1 to 120 characters",
      });
    }
    const body = parsed.data;
    if (body.label !== undefined) row.label = body.label;
    if (body.campaign !== undefined) row.campaign = body.campaign ?? null;
    if (body.partner_id !== undefined) {
      const partner = body.partner_id === null ? null : partnerRef(body.partner_id);
      if (partner === undefined) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          partner_id: "not found",
        });
      }
      row.partner = partner;
    }
    if (body.territory_id !== undefined) {
      const territory = body.territory_id === null ? null : territoryRef(body.territory_id);
      if (territory === undefined) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          territory_id: "not found",
        });
      }
      row.territory = territory;
    }
    if (body.is_active != null) row.is_active = body.is_active;
    return HttpResponse.json({ data: row });
  }),

  http.get(buildApiUrl("/public/lead-form"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const qr = new URL(request.url).searchParams.get("qr");
    const row = qr === null ? null : mockDb.qrCodes.find((item) => item.code === qr);
    if (qr !== null && (row === undefined || row === null || !row.is_active)) {
      return errorResponse(404, "not_found", "That code is not in use.");
    }
    const body: PublicLeadFormWire = {
      data: {
        qr:
          row == null
            ? null
            : {
                code: row.code,
                label: row.partner?.name ?? row.label,
                campaign: row.campaign,
                territory_id: row.territory?.id ?? null,
              },
        states: MOCK_TERRITORIES.filter((territory) => territory.level === "state").map(
          (territory) => ({ id: territory.id, name: territory.name }),
        ),
        mis_systems: mockLookupRows("mis-systems").map((row2) => ({
          code: row2.code,
          name: row2.name,
        })),
        inquiry_types: ["commercial", "subsidised", "industrial"],
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/public/territories"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const parentId = new URL(request.url).searchParams.get("parent_id");
    if (parentId === null || parentId === "") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        parent_id: "required",
      });
    }
    const children = MOCK_TERRITORIES.filter((territory) => territory.parent?.id === parentId)
      .slice(0, 200)
      .map((territory) => ({ id: territory.id, name: territory.name, level: territory.level }));
    return HttpResponse.json({ data: children });
  }),

  http.post(buildApiUrl("/public/leads/verify"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const mobile =
      typeof raw === "object" && raw !== null && "mobile" in raw && typeof raw.mobile === "string"
        ? normalizeIndianMobile(raw.mobile)
        : null;
    if (mobile === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        mobile: "a 10-digit Indian mobile",
      });
    }
    const sent = (mockDb.enquiryCodes.get(mobile) ?? 0) + 1;
    if (sent > 5) {
      return errorResponse(429, "rate_limited", "Too many codes for this number. Wait a while.");
    }
    mockDb.enquiryCodes.set(mobile, sent);
    return HttpResponse.json(
      {
        data: {
          sent: true,
          channel: "whatsapp",
          expires_in: EXPIRES_IN,
          resend_after: RESEND_AFTER,
        },
      },
      { status: 202 },
    );
  }),

  http.post(buildApiUrl("/public/leads"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const parsed = publicLeadSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        code: "six digits",
      });
    }
    const body = parsed.data;
    const mobile = normalizeIndianMobile(body.mobile);
    if (mobile === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        mobile: "a 10-digit Indian mobile",
      });
    }
    if (!mockDb.enquiryCodes.has(mobile) || body.code === MOCK_WRONG_ENQUIRY_CODE) {
      return errorResponse(422, "invalid_code", "That code is wrong, expired or used up.");
    }
    const earlier = mockDb.enquiriesToday.get(mobile);
    if (earlier !== undefined) {
      return HttpResponse.json({ data: { inquiry_no: earlier, created: false } });
    }
    const row = body.qr == null ? undefined : mockDb.qrCodes.find((item) => item.code === body.qr);
    if (body.qr != null && (row === undefined || !row.is_active)) {
      return errorResponse(404, "not_found", "That code is not in use.");
    }
    const territory = findMockTerritory(body.territory_id);
    if (territory === undefined || territory.level === "state") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        territory_id: "a district or taluka, never a state",
      });
    }
    const lead = createLeadFrom({
      farmer_name: body.farmer_name,
      mobile,
      email: null,
      territory_id: territory.id,
      village: body.village ?? null,
      inquiry_type: body.inquiry_type,
      mis_system: body.mis_system,
      source: row === undefined ? "website" : "qr_code",
      estimated_value: null,
      crops: [],
      land_acres: null,
      note: body.note ?? null,
    });
    if (lead instanceof Response) return lead;
    if (row?.partner != null) {
      lead.assigned_partner = row.partner;
    }
    if (row !== undefined) row.lead_count += 1;
    mockDb.leads = [lead, ...mockDb.leads];
    mockDb.enquiriesToday.set(mobile, lead.inquiry_no);
    return HttpResponse.json(
      { data: { inquiry_no: lead.inquiry_no, created: true } },
      { status: 201 },
    );
  }),
];
