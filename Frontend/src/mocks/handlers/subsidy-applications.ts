import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { LeadWire } from "@/features/leads/api/leads.schemas";
import {
  APPLICATION_DOCUMENT_MAX_BYTES,
  APPLICATION_DOCUMENT_TYPES,
  APPLICATION_DOCUMENTS_MAX,
  APPLICATION_STATUSES,
  type ApplicationDocumentWire,
  type ApplicationWire,
  type StageEntryWire,
} from "@/features/subsidy/api/subsidy-applications.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_SUBSIDY_CROPS } from "@/mocks/data/subsidy";
import {
  MOCK_DOCUMENT_TYPES,
  MOCK_STAGE_DEFS,
  type MockStageDef,
} from "@/mocks/data/subsidy-applications";
import { mockDb } from "@/mocks/db";

import { recordLeadEvent } from "./lead-events";
import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse, mockWorkbook } from "./shared";
import { calculate, checkCalculation, type CalculateBody } from "./subsidy";

/**
 * SUBS-004 … SUBS-008 · Subsidy applications, with the backend's rules: who may start one, the
 * stages in any order (a remark going back or repeating), the application closing itself once
 * every stage-16 amount has its stage-17 date, cancel, the checklist's files and the PIMS sheet.
 */

const SYSTEMS = ["drip", "mini_sprinkler", "sprinkler"] as const;
const FORWARDABLE: readonly LeadWire["stage"][] = ["qualified", "quoted", "negotiation", "won"];
const PAGE_SIZE = 25;
const SEED_COUNT = 6;
const FIRST_STAGE = MOCK_STAGE_DEFS[0];

/** The date a seeded stage entry records, so the ageing report has figures to show. */
const SEED_DATE_FIELD: Readonly<Record<string, string>> = {
  submitted_wo_pending: "submission",
  farmer_share: "supply",
  wo_issued: "wo_received",
  tpa_sent: "tpa_received",
  inspection_call_pending: "tpa_cleared",
  tr_pending: "inspection_sent",
  tr_done: "tr_date",
  fp_invoice_submitted: "fp_submitted",
};

interface Caller {
  readonly view: boolean;
  /** Start, record, upload and cancel need create or edit; view-only users get 403. */
  readonly write: boolean;
  readonly user: { readonly id: string; readonly full_name: string };
}

function caller(): Caller {
  const role = readMockRole();
  const permissions = mockPermissionsFor(role);
  const me = mockMeFor(role).data;
  return {
    view: can(permissions, "subsidy", "view"),
    write: can(permissions, "subsidy", "create") || can(permissions, "subsidy", "edit"),
    user: { id: me.id, full_name: me.full_name },
  };
}

function forbidden(): Response {
  return errorResponse(403, "forbidden", "No subsidy permission.");
}

function viewOnly(): Response {
  return errorResponse(403, "forbidden", "You may view applications but not change them.");
}

function invalid(fields: Record<string, string>, code = "validation_error"): Response {
  return errorResponse(422, code, "Some fields need correcting.", fields);
}

function moved(): Response {
  return errorResponse(409, "status_changed", "The application is closed or cancelled; reload it.");
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000);
}

function shiftDay(day: string, days: number): string {
  return new Date(Date.parse(day) + days * 86_400_000).toISOString().slice(0, 10);
}

function statusOf(application: ApplicationWire): ApplicationWire["status"] {
  return application.status;
}

function stageByCode(code: string): MockStageDef | undefined {
  return MOCK_STAGE_DEFS.find((stage) => stage.code === code);
}

// ── the store ─────────────────────────────────────────────────────────────────────

/** A plausible request for a lead's system, so a seeded application has figures. */
function seedCalculation(system: (typeof SYSTEMS)[number], index: number): CalculateBody {
  const crop = MOCK_SUBSIDY_CROPS[index % MOCK_SUBSIDY_CROPS.length]?.crop ?? null;
  if (system === "sprinkler") {
    return {
      system_type: "sprinkler",
      crops: [
        {
          crop,
          inter_crop: null,
          area: "1.200",
          crop_spacing: "",
          lateral_spacing: "12",
          lines: [],
        },
      ],
      nozzle: "plastic",
    };
  }
  return {
    system_type: system,
    crops: [
      {
        crop,
        inter_crop: null,
        area: (1 + (index % 3) * 0.5).toFixed(3),
        crop_spacing: "",
        lateral_spacing: "1.50",
        lines: [
          { description: "16 mm lateral, inline 4 lph", uom: "Mtr.", rate: "12.50", qty: "6500" },
          { description: "63 mm PVC sub-main", uom: "Mtr.", rate: "142.00", qty: "120" },
        ],
      },
    ],
    head_lines: [{ description: "Screen filter 25 m³/h", uom: "No.", rate: "6500.00", qty: "1" }],
    installation_rate_per_ha: "4000",
  };
}

function figuresFor(
  result: ReturnType<typeof calculate>,
  categoryCode: string,
): ApplicationWire["figures"] & { category: ApplicationWire["category"] } {
  let subsidy = 0;
  let farmerShare = 0;
  let category: ApplicationWire["category"] = { code: categoryCode, name: categoryCode, pct: "0" };
  for (const crop of result.crops) {
    const row = crop.categories.find((item) => item.code === categoryCode);
    if (row === undefined) continue;
    subsidy += Number(row.subsidy);
    farmerShare += Number(row.farmer_share);
    category = { code: row.code, name: row.name, pct: row.pct };
  }
  return {
    total_cost: result.total.blocks.total_incl_gst,
    subsidy: subsidy.toFixed(2),
    farmer_share: farmerShare.toFixed(2),
    category,
  };
}

function newApplication(
  lead: LeadWire,
  body: CalculateBody,
  categoryCode: string,
  surveyNo: string | null,
  createdOn: string,
): ApplicationWire {
  const serial = (mockDb.subsidyApplications?.length ?? 0) + 1;
  const result = calculate(body);
  const { category, ...figures } = figuresFor(result, categoryCode);
  const totalArea = body.crops.reduce((sum, crop) => sum + Number(crop.area), 0);
  const application: ApplicationWire = {
    id: mockUuid(MOCK_ID_SPACE.subsidyApplication, serial),
    application_no: `SA/GJ/2026-27/${String(serial).padStart(5, "0")}`,
    reg_no: null,
    status: "open",
    current_stage: {
      seq: FIRST_STAGE?.seq ?? 4,
      code: FIRST_STAGE?.code ?? "application_in_process",
      name: FIRST_STAGE?.name ?? "Application in process",
      since: createdOn,
    },
    scheme: "GGRC",
    system_type: body.system_type,
    category,
    lead: { id: lead.id, inquiry_no: lead.inquiry_no },
    farmer_name: lead.farmer_name,
    mobile: lead.mobile,
    village: lead.village,
    survey_no: surveyNo,
    territory: lead.territory,
    partner:
      lead.assigned_partner === null
        ? null
        : { id: lead.assigned_partner.id, name: lead.assigned_partner.name },
    total_area: totalArea.toFixed(3),
    group_total_area: body.group_total_area ?? null,
    figures,
    owner: lead.owner,
    owner_org_unit: lead.owner_org_unit,
    documents: { uploaded: 0, listed: MOCK_DOCUMENT_TYPES.length },
    ageing: { days_in_stage: 0, days_since_inward: null },
    full_fp_received_on: null,
    created_at: new Date(`${createdOn}T10:00:00+05:30`).toISOString(),
    cancellation: null,
  };
  mockDb.subsidyCalculations.set(application.id, result);
  return application;
}

function newEntry(
  application: ApplicationWire,
  stage: MockStageDef,
  occurredOn: string,
  values: Record<string, string | null>,
  remark: string | null,
  enteredBy: Caller["user"] | null,
): StageEntryWire {
  const entries = mockDb.subsidyEntries.get(application.id) ?? [];
  const entry: StageEntryWire = {
    id: mockUuid(
      MOCK_ID_SPACE.subsidyEntry,
      [...mockDb.subsidyEntries.values()].reduce((sum, list) => sum + list.length, 0) + 1,
    ),
    stage: { seq: stage.seq, code: stage.code, name: stage.name, since: occurredOn },
    occurred_on: occurredOn,
    values,
    remark,
    entered_by: enteredBy,
    entered_at: new Date().toISOString(),
  };
  mockDb.subsidyEntries.set(application.id, [...entries, entry]);
  return entry;
}

/** The latest value of each field, across every entry. */
export function latestValues(applicationId: string): Record<string, string | null> {
  const values: Record<string, string | null> = {};
  for (const entry of mockDb.subsidyEntries.get(applicationId) ?? []) {
    Object.assign(values, entry.values);
  }
  return values;
}

/** Re-derives what follows from the entries: stage, Reg. No., ageing, closing. */
function refresh(application: ApplicationWire): void {
  const entries = mockDb.subsidyEntries.get(application.id) ?? [];
  const last = entries.at(-1);
  if (last !== undefined) application.current_stage = last.stage;
  const values = latestValues(application.id);
  const regNo = values.reg_no;
  if (regNo !== undefined) application.reg_no = regNo === null || regNo === "" ? null : regNo;
  const today = todayInIndia();
  const firstInward = entries.find((entry) => entry.stage.code === FIRST_STAGE?.code);
  const inward = values.app_inward ?? firstInward?.occurred_on ?? null;
  application.ageing = {
    days_in_stage: daysBetween(application.current_stage.since, today),
    days_since_inward: inward === null ? null : daysBetween(inward, today),
  };
  const files = mockDb.subsidyDocuments.get(application.id);
  application.documents = {
    uploaded:
      files === undefined ? 0 : [...files.values()].filter((list) => list.length > 0).length,
    listed: MOCK_DOCUMENT_TYPES.length,
  };
  // Closes once every stage-16 amount entered has its stage-17 received date.
  const amounts = MOCK_STAGE_DEFS.flatMap((stage) => stage.fields).filter(
    (field) => field.pairsWith !== undefined,
  );
  const entered = amounts.filter((field) => (values[field.key] ?? "") !== "");
  if (
    application.status === "open" &&
    entered.length > 0 &&
    entered.every((field) => (values[field.pairsWith ?? ""] ?? "") !== "")
  ) {
    application.status = "full_fp_received";
    application.full_fp_received_on = today;
  }
}

/** Seeds a few applications from subsidised leads on first use, at different stages. */
export function mockApplications(): ApplicationWire[] {
  if (mockDb.subsidyApplications !== null) return mockDb.subsidyApplications;
  mockDb.subsidyApplications = [];
  const today = todayInIndia();
  const leads = mockDb.leads.filter(
    (lead) =>
      lead.inquiry_type === "subsidised" &&
      lead.stage === "won" &&
      SYSTEMS.some((system) => system === lead.mis_system),
  );
  leads.slice(0, SEED_COUNT).forEach((lead, index) => {
    const system = SYSTEMS.find((item) => item === lead.mis_system) ?? "drip";
    const started = shiftDay(today, -(60 - index * 9));
    const application = newApplication(
      lead,
      seedCalculation(system, index),
      index % 3 === 2 ? "sc_st" : "small_farmer",
      index % 2 === 0 ? `${String(100 + index)}/2` : null,
      started,
    );
    mockDb.subsidyApplications?.unshift(application);
    const first = MOCK_STAGE_DEFS[0];
    if (first !== undefined) {
      newEntry(
        application,
        first,
        started,
        {
          app_inward: started,
          reg_no: index > 0 ? `GGRC/24/${String(index).padStart(3, "0")}` : null,
        },
        null,
        lead.owner,
      );
    }
    // Later applications have moved further along.
    MOCK_STAGE_DEFS.slice(1, 1 + index * 2).forEach((stage, step) => {
      const shifted = shiftDay(started, (step + 1) * 2);
      // Never after today: a business date can't be in the future.
      const day = shifted > today ? today : shifted;
      const key = SEED_DATE_FIELD[stage.code];
      newEntry(application, stage, day, key === undefined ? {} : { [key]: day }, null, lead.owner);
    });
    if (index === SEED_COUNT - 1) {
      application.status = "cancelled";
      application.cancellation = { reason: "The farmer chose a commercial purchase instead." };
    }
    refresh(application);
  });
  return mockDb.subsidyApplications;
}

function findApplication(applicationId: unknown): ApplicationWire | Response {
  const found = mockApplications().find((item) => item.id === applicationId);
  return found ?? errorResponse(404, "not_found", "Not an application in your scope.");
}

function documentsOf(applicationId: string): Map<string, ApplicationDocumentWire[]> {
  const known = mockDb.subsidyDocuments.get(applicationId);
  if (known !== undefined) return known;
  const fresh = new Map<string, ApplicationDocumentWire[]>();
  mockDb.subsidyDocuments.set(applicationId, fresh);
  return fresh;
}

function objectUrlOf(file: Blob): string {
  try {
    return URL.createObjectURL(file);
  } catch {
    return "/icon.svg";
  }
}

// ── request shapes ────────────────────────────────────────────────────────────────

const createSchema = z.object({
  lead_id: z.string().min(1),
  category_code: z.string().min(1).max(60),
  calculation: z.unknown(),
  survey_no: z.string().max(100).nullish(),
});

const stageSchema = z.object({
  stage_code: z.string().min(1).max(60),
  occurred_on: z.iso.date(),
  values: z.record(z.string(), z.string().nullable()).default({}),
  remark: z.string().trim().max(1000).nullish(),
});

const cancelSchema = z.object({ reason: z.string().trim().min(1).max(500) });

/** The backend's per-type checks on a stage's values. */
function valueProblems(
  stage: MockStageDef,
  values: Record<string, string | null>,
): Record<string, string> {
  const fields: Record<string, string> = {};
  const today = todayInIndia();
  for (const [key, value] of Object.entries(values)) {
    const field = stage.fields.find((item) => item.key === key);
    const at = `values.${key}`;
    if (field === undefined) {
      fields[at] = "not a field of this stage";
      continue;
    }
    if (value === null || value === "") continue;
    if (field.type === "date") {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) fields[at] = "a date, YYYY-MM-DD";
      else if (value > today) fields[at] = "not after today";
    } else if (field.type === "amount") {
      if (!/^\d+(\.\d{1,2})?$/.test(value)) fields[at] = "an amount, at most two decimals";
      else if (Number(value) >= 1e12) fields[at] = "too large";
    } else if (value.length > 500) {
      fields[at] = "up to 500 characters";
    }
  }
  return fields;
}

const base = (rest = ""): string => buildApiUrl(`/subsidy-applications${rest}`);

export const subsidyApplicationHandlers = [
  http.get(buildApiUrl("/subsidy-stages"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    return HttpResponse.json({
      data: MOCK_STAGE_DEFS.map((stage) => ({
        seq: stage.seq,
        code: stage.code,
        name: stage.name,
        fields: stage.fields.map((field) => ({
          key: field.key,
          label: field.label,
          type: field.type,
          required: false,
        })),
      })),
    });
  }),

  http.get(base(), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const stage = url.searchParams.get("stage");
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const leadId = url.searchParams.get("lead_id");
    if (status !== null && !APPLICATION_STATUSES.some((item) => item === status)) {
      return invalid({ status: "open, full_fp_received or cancelled" });
    }
    const rows =
      scenario === "empty"
        ? []
        : mockApplications().filter(
            (row) =>
              (status === null || row.status === status) &&
              (stage === null || row.current_stage.code === stage) &&
              (leadId === null || row.lead.id === leadId) &&
              (q === "" ||
                row.application_no.toLowerCase().includes(q) ||
                (row.reg_no ?? "").toLowerCase().includes(q) ||
                row.farmer_name.toLowerCase().includes(q)),
          );
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? PAGE_SIZE);
    const page = rows.slice(offset, offset + limit);
    return HttpResponse.json({
      data: page,
      meta: { next_cursor: offset + limit < rows.length ? encodeCursor(offset + limit) : null },
    });
  }),

  http.get(base("/export"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    return mockWorkbook(
      "subsidy-applications",
      ["Application No.", "Reg. No.", "Farmer", "Stage", "Days in stage", "Status"],
      mockApplications().map((row) => [
        row.application_no,
        row.reg_no ?? "",
        row.farmer_name,
        row.current_stage.name,
        String(row.ageing.days_in_stage),
        row.status,
      ]),
    );
  }),

  http.post(base(), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    if (!who.view) return forbidden();
    if (!who.write) return viewOnly();
    const raw = await request.text();
    const key = request.headers.get("idempotency-key");
    const replay = key === null ? undefined : mockDb.subsidyWrites.get(key);
    if (replay !== undefined) {
      if (replay.body !== raw) {
        return errorResponse(
          409,
          "idempotency_key_reused",
          "That key was used for another request.",
        );
      }
      const earlier = mockApplications().find((item) => item.id === replay.applicationId);
      if (earlier !== undefined) return HttpResponse.json({ data: earlier }, { status: 201 });
    }
    const parsed = createSchema.safeParse(JSON.parse(raw));
    if (!parsed.success) return invalid({ lead_id: "required", category_code: "required" });
    const lead = mockDb.leads.find((item) => item.id === parsed.data.lead_id);
    if (lead === undefined) return errorResponse(404, "not_found", "Not a lead in your scope.");
    if (lead.inquiry_type !== "subsidised") {
      return invalid(
        { lead_id: "the lead's inquiry type is not subsidised" },
        "lead_not_subsidised",
      );
    }
    if (!FORWARDABLE.includes(lead.stage)) {
      return invalid(
        { lead_id: "the lead is not qualified, quoted, in negotiation or won" },
        "lead_not_forwardable",
      );
    }
    const system = SYSTEMS.find((item) => item === lead.mis_system);
    if (system === undefined) {
      return invalid(
        { lead_id: "the lead's system has no subsidy calculation" },
        "lead_system_not_subsidised",
      );
    }
    if (
      mockApplications().some((item) => item.lead.id === lead.id && item.status !== "cancelled")
    ) {
      return invalid({ lead_id: "the lead already has a live application" }, "already_forwarded");
    }
    const checked = checkCalculation(parsed.data.calculation);
    if ("fields" in checked) {
      return invalid(
        Object.fromEntries(
          Object.entries(checked.fields).map(([path, reason]) => [`calculation.${path}`, reason]),
        ),
      );
    }
    if (checked.body.system_type !== system) {
      return invalid({ "calculation.system_type": "must be the lead's system" });
    }
    const result = calculate(checked.body);
    const notApplying = result.crops.find(
      (crop) =>
        crop.categories.find((row) => row.code === parsed.data.category_code)?.applicable !== true,
    );
    if (notApplying !== undefined) {
      return invalid({
        category_code: `does not apply on ${notApplying.crop ?? "a crop"}; choose another category`,
      });
    }
    const today = todayInIndia();
    const application = newApplication(
      lead,
      checked.body,
      parsed.data.category_code,
      parsed.data.survey_no?.trim() || null,
      today,
    );
    mockApplications().unshift(application);
    if (FIRST_STAGE !== undefined) newEntry(application, FIRST_STAGE, today, {}, null, who.user);
    refresh(application);
    if (lead.stage !== "won") {
      recordLeadEvent(lead, "lead.stage_changed", {
        from: lead.stage,
        to: "won",
        via: "subsidy_application",
      });
      lead.stage = "won";
    }
    recordLeadEvent(lead, "subsidy.created", { application_no: application.application_no });
    if (key !== null) mockDb.subsidyWrites.set(key, { body: raw, applicationId: application.id });
    return HttpResponse.json({ data: application }, { status: 201 });
  }),

  http.get(base("/:applicationId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    refresh(application);
    return HttpResponse.json({ data: application });
  }),

  http.get(base("/:applicationId/calculation"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    const stored = mockDb.subsidyCalculations.get(application.id);
    if (stored === undefined) return errorResponse(404, "not_found", "No stored calculation.");
    return HttpResponse.json({ data: stored });
  }),

  http.get(base("/:applicationId/stages"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    return HttpResponse.json({ data: mockDb.subsidyEntries.get(application.id) ?? [] });
  }),

  http.post(base("/:applicationId/stages"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    if (!who.view) return forbidden();
    if (!who.write) return viewOnly();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    if (application.status !== "open") return moved();
    const parsed = stageSchema.safeParse(await request.json());
    if (!parsed.success) {
      const fields: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        fields[issue.path.map(String).join(".")] =
          issue.path[0] === "values" ? "a string or null, never a number" : issue.message;
      }
      return invalid(fields);
    }
    const body = parsed.data;
    const stage = stageByCode(body.stage_code);
    if (stage === undefined) return invalid({ stage_code: "not a stage of this scheme" });
    if (body.occurred_on > todayInIndia()) return invalid({ occurred_on: "not after today" });
    const problems = valueProblems(stage, body.values);
    if (Object.keys(problems).length > 0) return invalid(problems);
    const remark = body.remark?.trim() || null;
    if (stage.seq <= application.current_stage.seq && remark === null) {
      return invalid({ remark: "a remark is needed going back, or for the same stage" });
    }
    const values = Object.fromEntries(
      Object.entries(body.values).map(([key, value]) => [key, value === "" ? null : value]),
    );
    const before = application.current_stage.seq;
    newEntry(application, stage, body.occurred_on, values, remark, who.user);
    refresh(application);
    const lead = mockDb.leads.find((item) => item.id === application.lead.id);
    if (lead !== undefined) {
      recordLeadEvent(lead, "subsidy.stage_recorded", {
        application_no: application.application_no,
        stage: stage.name,
        direction: stage.seq > before ? "forward" : stage.seq === before ? "same" : "back",
      });
      // Read afresh: recording the stage may just have closed it.
      if (statusOf(application) === "full_fp_received") {
        recordLeadEvent(lead, "subsidy.closed", { application_no: application.application_no });
      }
    }
    return HttpResponse.json({ data: application }, { status: 201 });
  }),

  http.post(base("/:applicationId/cancel"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    if (!who.view) return forbidden();
    if (!who.write) return viewOnly();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    if (application.status !== "open") return moved();
    const parsed = cancelSchema.safeParse(await request.json());
    if (!parsed.success) return invalid({ reason: "1 to 500 characters" });
    application.status = "cancelled";
    application.cancellation = { reason: parsed.data.reason };
    const lead = mockDb.leads.find((item) => item.id === application.lead.id);
    if (lead !== undefined) {
      recordLeadEvent(lead, "subsidy.cancelled", {
        application_no: application.application_no,
        reason: parsed.data.reason,
      });
    }
    return HttpResponse.json({ data: application });
  }),

  http.get(base("/:applicationId/documents"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    const files = documentsOf(application.id);
    return HttpResponse.json({
      data: MOCK_DOCUMENT_TYPES.map((type, index) => ({
        type: {
          id: mockUuid(MOCK_ID_SPACE.subsidyDocument, 0x100 + index),
          code: type.code,
          name: type.name,
          is_active: true,
        },
        files: files.get(type.code) ?? [],
      })),
    });
  }),

  http.post(base("/:applicationId/documents"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    if (!who.view) return forbidden();
    if (!who.write) return viewOnly();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    if (application.status === "cancelled") return moved();
    const form = await request.formData();
    const file = form.get("file");
    const documentType = form.get("document_type");
    // A shape check, not `instanceof File`: the parsed part may come from another realm.
    if (file === null || typeof file === "string") return invalid({ file: "a file is needed" });
    if (
      typeof documentType !== "string" ||
      !MOCK_DOCUMENT_TYPES.some((type) => type.code === documentType)
    ) {
      return invalid({ document_type: "not on the checklist" });
    }
    if (file.size === 0) return invalid({ file: "empty" });
    if (file.size > APPLICATION_DOCUMENT_MAX_BYTES) {
      return errorResponse(413, "payload_too_large", "Up to 10 MB.");
    }
    if (!APPLICATION_DOCUMENT_TYPES.some((type) => type === file.type)) {
      return errorResponse(422, "attachment_type", "PDF, JPEG, PNG, WebP or HEIC only.", {
        file: "not an accepted type",
      });
    }
    const files = documentsOf(application.id);
    const all = [...files.values()].flat();
    const same = all.find((item) => item.filename === file.name && item.size_bytes === file.size);
    if (same !== undefined) return HttpResponse.json({ data: same });
    if (all.length >= APPLICATION_DOCUMENTS_MAX) {
      return errorResponse(422, "too_many_documents", "Up to 40 files per application.");
    }
    const document: ApplicationDocumentWire = {
      id: mockUuid(MOCK_ID_SPACE.subsidyDocument, mockDb.subsidyFiles.size + 1),
      content_type: file.type,
      size_bytes: file.size,
      filename: file.name,
      uploaded_by: who.user,
      created_at: new Date().toISOString(),
    };
    mockDb.subsidyFiles.set(document.id, file);
    files.set(documentType, [...(files.get(documentType) ?? []), document]);
    refresh(application);
    const lead = mockDb.leads.find((item) => item.id === application.lead.id);
    if (lead !== undefined) {
      recordLeadEvent(lead, "subsidy.document_added", {
        application_no: application.application_no,
        document_type: documentType,
      });
    }
    return HttpResponse.json({ data: document }, { status: 201 });
  }),

  http.get(base("/:applicationId/documents/:documentId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    const known = [...documentsOf(application.id).values()]
      .flat()
      .some((item) => item.id === params.documentId);
    if (!known) return errorResponse(404, "not_found", "No such file.");
    const file =
      typeof params.documentId === "string"
        ? mockDb.subsidyFiles.get(params.documentId)
        : undefined;
    return HttpResponse.json({
      data: {
        url: file === undefined ? "/icon.svg" : objectUrlOf(file),
        expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
      },
    });
  }),

  http.get(base("/:applicationId/pims.xlsx"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!caller().view) return forbidden();
    const application = findApplication(params.applicationId);
    if (application instanceof Response) return application;
    return mockWorkbook(
      `pims-${application.application_no.replaceAll("/", "-")}`,
      [
        "CostType",
        "Crop",
        "ItemCode",
        "Item",
        "Size",
        "Unit",
        "Rate",
        "Quantity",
        "Amount",
        "Remark",
      ],
      [],
    );
  }),
];
