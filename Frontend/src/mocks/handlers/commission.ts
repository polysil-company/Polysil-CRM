import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  COMMISSION_STATUSES,
  RATE_PARTNER_TYPES,
  RATE_SYSTEM_TYPES,
  type CommissionPreviewWire,
  type CommissionWire,
  type RateWire,
} from "@/features/commission/api/commission.schemas";
import type { ApplicationWire } from "@/features/subsidy/api/subsidy-applications.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can, type ModuleCode } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockCommissionId, mockRateId, money, workOutCommission } from "@/mocks/data/commission";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse, mockWorkbook } from "./shared";
import { mockApplications } from "./subsidy-applications";

/**
 * SUBS-016 … SUBS-018 · Dealer commission and TOD (FS-033, `docs/api/dealer-commission.md`).
 * Permissions as the backend's router: subsidy.view reads and cancels before approval,
 * subsidy.edit records, payments.approve approves and returns, payments.edit pays,
 * masters.edit adds rates.
 */

function allowed(module: ModuleCode, action: "view" | "create" | "edit" | "approve"): boolean {
  return can(mockPermissionsFor(readMockRole()), module, action);
}

/**
 * Who is acting. Every mock staff role signs in as the same user, so the role is part of the id
 * here: otherwise Accounts would count as the recorder of what Admin recorded (own_decision).
 */
function me(): { id: string; name: string } {
  const role = readMockRole();
  const user = mockMeFor(role).data;
  return { id: `${user.id}:${role}`, name: user.full_name };
}

function forbidden(message = "Not permitted."): Response {
  return errorResponse(403, "forbidden", message);
}

function remarkRequired(): Response {
  return errorResponse(422, "remark_required", "Say why.", { remark: "Say why." });
}

function partnerTypeOf(partnerId: string): string | null {
  return mockDb.partners.find((partner) => partner.id === partnerId)?.partner_type ?? null;
}

/** The most specific rate in force on a day: one partner, then type, then system, then scheme. */
function rateFor(application: ApplicationWire, on: string): RateWire | null {
  const partnerId = application.partner?.id ?? null;
  const partnerType = partnerId === null ? null : partnerTypeOf(partnerId);
  const fits = mockDb.commissionRates.filter(
    (rate) =>
      rate.scheme === application.scheme &&
      rate.effective_from <= on &&
      (rate.partner === null || rate.partner.id === partnerId) &&
      (rate.partner_type === null || rate.partner_type === partnerType) &&
      (rate.system_type === null || rate.system_type === application.system_type),
  );
  const rank = (rate: RateWire): number =>
    (rate.partner === null ? 0 : 8) +
    (rate.partner_type === null ? 0 : 4) +
    (rate.system_type === null ? 0 : 2);
  const [best] = [...fits].sort(
    (left, right) =>
      rank(right) - rank(left) || right.effective_from.localeCompare(left.effective_from),
  );
  // A 0% rate retires the scope: no commission is due.
  return best === undefined || Number(best.commission_pct) === 0 ? null : best;
}

function previewOf(application: ApplicationWire): CommissionPreviewWire | Response {
  if (application.status !== "full_fp_received") {
    return errorResponse(409, "not_closed", "Stage 18 comes after every payment is received.");
  }
  if (application.partner === null) {
    return errorResponse(422, "no_partner", "This application has no dealer.");
  }
  const blocks = mockDb.subsidyCalculations.get(application.id)?.total.blocks;
  const rate = rateFor(application, application.full_fp_received_on ?? todayInIndia());
  return {
    partner: { id: application.partner.id, name: application.partner.name },
    cost_excl_gst: blocks?.cost_excl_gst ?? "0.00",
    a_plus_b: blocks?.a_plus_b ?? null,
    installation: blocks?.installation ?? "0.00",
    commission_pct: rate?.commission_pct ?? null,
    tod_pct: rate?.tod_pct ?? null,
    rate_id: rate?.id ?? null,
  };
}

function findApplication(applicationId: unknown): ApplicationWire | Response {
  const found = mockApplications().find((item) => item.id === applicationId);
  return found ?? errorResponse(404, "not_found", "Not an application in your scope.");
}

/** Commissions, newest first; the paid-up seeded application starts with one to approve. */
export function mockCommissions(): CommissionWire[] {
  if (mockDb.commissions !== null) return mockDb.commissions;
  mockDb.commissions = [];
  const closed = mockApplications().find(
    (application) => application.status === "full_fp_received" && application.partner !== null,
  );
  if (closed === undefined) return mockDb.commissions;
  const preview = previewOf(closed);
  if (preview instanceof Response || preview.commission_pct === null) return mockDb.commissions;
  const gi = 2400;
  const pvc = 1800;
  const recordedAt = `${closed.full_fp_received_on ?? todayInIndia()}T11:00:00.000Z`;
  mockDb.commissions.push({
    id: mockCommissionId(1),
    application: { id: closed.id, application_no: closed.application_no, reg_no: closed.reg_no },
    partner: preview.partner,
    status: "calculated",
    cost_excl_gst: preview.cost_excl_gst,
    a_plus_b: preview.a_plus_b,
    gi_fitting: money(gi),
    pvc_hdpe_fitting: money(pvc),
    installation: preview.installation,
    commission_pct: preview.commission_pct,
    tod_pct: preview.tod_pct ?? "0.00",
    ...workOutCommission({
      costExclGst: Number(preview.cost_excl_gst),
      gi,
      pvc,
      installation: Number(preview.installation),
      todBase: null,
      commissionPct: Number(preview.commission_pct),
      todPct: Number(preview.tod_pct ?? "0"),
    }),
    remark: null,
    // A co-ordinator recorded it, so Admin and Accounts may both approve it.
    recorded_by: { id: "usr-coordinator", name: "Meera Shah" },
    recorded_at: recordedAt,
    decided_by: null,
    decided_at: null,
    decision_remark: null,
    paid_on: null,
    payment_reference: null,
  });
  return mockDb.commissions;
}

/** The application's live commission: the newest one not cancelled. */
function liveOf(applicationId: string): CommissionWire | undefined {
  return mockCommissions().find(
    (commission) =>
      commission.application.id === applicationId && commission.status !== "cancelled",
  );
}

const amount = z.union([z.number(), z.string()]).transform((value, ctx) => {
  const number = Number(value);
  if (String(value).trim() === "" || !Number.isFinite(number)) {
    ctx.addIssue({ code: "custom", message: "A number." });
    return z.NEVER;
  }
  return number;
});

const recordSchema = z.object({
  gi_fitting: amount.default(0),
  pvc_hdpe_fitting: amount.default(0),
  installation: amount.nullish(),
  tod_base: amount.nullish(),
  remark: z.string().nullish(),
});

function fieldsOf(error: z.ZodError): Record<string, string> {
  return Object.fromEntries(
    error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
  );
}

function decisionTarget(commissionId: unknown): CommissionWire | Response {
  const found = mockCommissions().find((commission) => commission.id === commissionId);
  return found ?? errorResponse(404, "not_found", "No such commission.");
}

function moved(commission: CommissionWire): Response {
  return errorResponse(409, "status_changed", `It is ${commission.status} now.`, {
    status: commission.status,
  });
}

function decide(
  commission: CommissionWire,
  status: CommissionWire["status"],
  remark: string | null,
): Response {
  const by = me();
  commission.status = status;
  commission.decided_by = { id: by.id, name: by.name };
  commission.decided_at = new Date().toISOString();
  commission.decision_remark = remark;
  return HttpResponse.json({ data: commission });
}

async function remarkOf(request: Request): Promise<string | null> {
  const raw: unknown = await request.json().catch(() => ({}));
  const parsed = z.object({ remark: z.string().nullish() }).safeParse(raw);
  const remark = parsed.success ? (parsed.data.remark ?? "").trim() : "";
  return remark === "" ? null : remark;
}

const rateSchema = z.object({
  scheme: z.string().min(1).default("GGRC"),
  system_type: z.enum(RATE_SYSTEM_TYPES).nullish(),
  partner_type: z.enum(RATE_PARTNER_TYPES).nullish(),
  partner_id: z.string().min(1).nullish(),
  commission_pct: amount.refine((value) => value >= 0 && value <= 100, "Between 0 and 100."),
  tod_pct: amount.refine((value) => value >= 0 && value <= 100, "Between 0 and 100."),
  effective_from: z.iso.date({ message: "A date." }),
});

export const commissionHandlers = [
  http.get(
    buildApiUrl("/subsidy-applications/:applicationId/commission/preview"),
    async ({ params }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!allowed("subsidy", "view")) return forbidden();
      const application = findApplication(params.applicationId);
      if (application instanceof Response) return application;
      const preview = previewOf(application);
      return preview instanceof Response ? preview : HttpResponse.json({ data: preview });
    },
  ),

  http.get(buildApiUrl("/subsidy-applications/:applicationId/commission"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("subsidy", "view")) return forbidden();
    const live = liveOf(String(params.applicationId));
    return live === undefined
      ? errorResponse(404, "not_found", "No commission recorded.")
      : HttpResponse.json({ data: live });
  }),

  http.post(
    buildApiUrl("/subsidy-applications/:applicationId/commission"),
    async ({ params, request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!allowed("subsidy", "edit")) return forbidden();
      const application = findApplication(params.applicationId);
      if (application instanceof Response) return application;
      const preview = previewOf(application);
      if (preview instanceof Response) return preview;
      if (preview.commission_pct === null) {
        return errorResponse(422, "no_rate", "No commission rate is in force for this dealer.");
      }
      const parsed = recordSchema.safeParse(await request.json());
      if (!parsed.success) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          ...fieldsOf(parsed.error),
        });
      }
      const body = parsed.data;
      const installation = body.installation ?? Number(preview.installation);
      const negative = Object.entries({
        gi_fitting: body.gi_fitting,
        pvc_hdpe_fitting: body.pvc_hdpe_fitting,
        installation,
        tod_base: body.tod_base ?? 0,
      }).filter(([, value]) => value < 0);
      if (negative.length > 0) {
        return errorResponse(
          422,
          "validation_error",
          "Some fields need correcting.",
          Object.fromEntries(negative.map(([field]) => [field, "Not below zero."])),
        );
      }
      const cost = Number(preview.cost_excl_gst);
      if (body.gi_fitting + body.pvc_hdpe_fitting + installation > cost) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          gi_fitting: "The fittings and installation come to more than the cost.",
        });
      }
      const live = liveOf(application.id);
      if (live !== undefined && (live.status === "approved" || live.status === "paid")) {
        return errorResponse(409, "commission_exists", `It is already ${live.status}.`);
      }
      const by = me();
      const figures = {
        cost_excl_gst: preview.cost_excl_gst,
        a_plus_b: preview.a_plus_b,
        gi_fitting: money(body.gi_fitting),
        pvc_hdpe_fitting: money(body.pvc_hdpe_fitting),
        installation: money(installation),
        commission_pct: preview.commission_pct,
        tod_pct: preview.tod_pct ?? "0.00",
        ...workOutCommission({
          costExclGst: cost,
          gi: body.gi_fitting,
          pvc: body.pvc_hdpe_fitting,
          installation,
          todBase: body.tod_base ?? null,
          commissionPct: Number(preview.commission_pct),
          todPct: Number(preview.tod_pct ?? "0"),
        }),
        remark: body.remark?.trim() === "" ? null : (body.remark?.trim() ?? null),
        recorded_by: { id: by.id, name: by.name },
        recorded_at: new Date().toISOString(),
        decided_by: null,
        decided_at: null,
        decision_remark: null,
        paid_on: null,
        payment_reference: null,
        status: "calculated" as const,
      };
      if (live !== undefined) {
        Object.assign(live, figures);
        return HttpResponse.json({ data: live }, { status: 201 });
      }
      const commission: CommissionWire = {
        id: mockCommissionId(100 + mockCommissions().length),
        application: {
          id: application.id,
          application_no: application.application_no,
          reg_no: application.reg_no,
        },
        partner: preview.partner,
        ...figures,
      };
      mockCommissions().unshift(commission);
      return HttpResponse.json({ data: commission }, { status: 201 });
    },
  ),

  // Before /:commissionId, which would read "export" as an id.
  http.get(buildApiUrl("/dealer-commissions/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("subsidy", "view") && !allowed("payments", "view")) return forbidden();
    const statuses = new URL(request.url).searchParams.get("status")?.split(",") ?? [];
    const rows = mockCommissions().filter(
      (commission) => statuses.length === 0 || statuses.includes(commission.status),
    );
    return mockWorkbook(
      "dealer-commissions",
      ["Application", "Dealer", "Status", "Commission", "TOD", "Total", "Paid on"],
      rows.map((row) => [
        row.application.application_no,
        row.partner.name ?? "",
        row.status,
        row.commission_amount,
        row.tod_amount,
        row.total,
        row.paid_on ?? "",
      ]),
    );
  }),

  http.get(buildApiUrl("/dealer-commissions"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("subsidy", "view") && !allowed("payments", "view")) return forbidden();
    const raw = new URL(request.url).searchParams.get("status");
    const statuses = raw === null ? [] : raw.split(",");
    if (statuses.some((status) => !COMMISSION_STATUSES.some((known) => known === status))) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        status: COMMISSION_STATUSES.join(", "),
      });
    }
    const rows = mockCommissions().filter(
      (commission) => statuses.length === 0 || statuses.includes(commission.status),
    );
    return HttpResponse.json({ data: rows, meta: { limit: 50, next_cursor: null } });
  }),

  http.get(buildApiUrl("/dealer-commissions/:commissionId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("subsidy", "view") && !allowed("payments", "view")) return forbidden();
    const commission = decisionTarget(params.commissionId);
    return commission instanceof Response ? commission : HttpResponse.json({ data: commission });
  }),

  http.post(buildApiUrl("/dealer-commissions/:commissionId/approve"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("payments", "approve")) return forbidden();
    const commission = decisionTarget(params.commissionId);
    if (commission instanceof Response) return commission;
    if (commission.status !== "calculated") return moved(commission);
    if (commission.recorded_by.id === me().id) {
      return errorResponse(403, "own_decision", "Someone else approves what you recorded.");
    }
    return decide(commission, "approved", null);
  }),

  http.post(
    buildApiUrl("/dealer-commissions/:commissionId/return"),
    async ({ params, request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!allowed("payments", "approve")) return forbidden();
      const commission = decisionTarget(params.commissionId);
      if (commission instanceof Response) return commission;
      const remark = await remarkOf(request);
      if (remark === null) return remarkRequired();
      if (commission.status !== "calculated") return moved(commission);
      return decide(commission, "returned", remark);
    },
  ),

  http.post(
    buildApiUrl("/dealer-commissions/:commissionId/cancel"),
    async ({ params, request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!allowed("subsidy", "view")) return forbidden();
      const commission = decisionTarget(params.commissionId);
      if (commission instanceof Response) return commission;
      const remark = await remarkOf(request);
      if (remark === null) return remarkRequired();
      // The co-ordinator before approval; Accounts once approved.
      if (commission.status === "approved" && !allowed("payments", "approve")) {
        return forbidden("Accounts cancels an approved commission.");
      }
      if (!["calculated", "returned", "approved"].includes(commission.status)) {
        return moved(commission);
      }
      return decide(commission, "cancelled", remark);
    },
  ),

  http.post(buildApiUrl("/dealer-commissions/:commissionId/pay"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("payments", "edit")) return forbidden();
    const commission = decisionTarget(params.commissionId);
    if (commission instanceof Response) return commission;
    const parsed = z
      .object({
        paid_on: z.iso.date({ message: "A date." }),
        payment_reference: z.string().trim().min(1, "Give the payment reference."),
      })
      .safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldsOf(parsed.error),
      );
    }
    if (parsed.data.paid_on > todayInIndia()) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        paid_on: "Not in the future.",
      });
    }
    if (commission.status !== "approved") return moved(commission);
    commission.status = "paid";
    commission.paid_on = parsed.data.paid_on;
    commission.payment_reference = parsed.data.payment_reference;
    return HttpResponse.json({ data: commission });
  }),

  http.get(buildApiUrl("/commission-rates"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (
      !allowed("subsidy", "view") &&
      !allowed("payments", "view") &&
      !allowed("masters", "edit")
    ) {
      return forbidden();
    }
    const scheme = new URL(request.url).searchParams.get("scheme") ?? "GGRC";
    const rates = mockDb.commissionRates
      .filter((rate) => rate.scheme === scheme)
      .sort((left, right) => right.effective_from.localeCompare(left.effective_from));
    return HttpResponse.json({ data: rates });
  }),

  http.post(buildApiUrl("/commission-rates"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("masters", "edit")) return forbidden();
    const parsed = rateSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldsOf(parsed.error),
      );
    }
    const body = parsed.data;
    if (!mockDb.subsidySchemes.some((scheme) => scheme.code === body.scheme)) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        scheme: "Unknown scheme.",
      });
    }
    const partner =
      body.partner_id == null ? null : mockDb.partners.find((item) => item.id === body.partner_id);
    if (partner === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        partner_id: "No such partner in your scope.",
      });
    }
    const scope = (rate: RateWire): string =>
      [
        rate.scheme,
        rate.system_type,
        rate.partner_type,
        rate.partner?.id,
        rate.effective_from,
      ].join("|");
    const rate: RateWire = {
      id: mockRateId(100 + mockDb.commissionRates.length),
      scheme: body.scheme,
      system_type: body.system_type ?? null,
      partner_type: body.partner_type ?? null,
      partner: partner === null ? null : { id: partner.id, name: partner.name },
      commission_pct: body.commission_pct.toFixed(2),
      tod_pct: body.tod_pct.toFixed(2),
      effective_from: body.effective_from,
    };
    if (mockDb.commissionRates.some((existing) => scope(existing) === scope(rate))) {
      return errorResponse(409, "rate_exists", "A rate for the same scope starts that day.");
    }
    mockDb.commissionRates.unshift(rate);
    return HttpResponse.json({ data: rate }, { status: 201 });
  }),
];
