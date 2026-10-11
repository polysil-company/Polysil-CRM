import { http, HttpResponse } from "msw";

import type { ApplicationWire } from "@/features/subsidy/api/subsidy-applications.schemas";
import {
  AGEING_FIGURES,
  type AgeingFigureKey,
  type AgeRowWire,
  type StageRowWire,
  type SupplyRowWire,
} from "@/features/subsidy/api/subsidy-reports.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_STAGE_DEFS } from "@/mocks/data/subsidy-applications";
import { mockTerritoryLineage } from "@/mocks/data/territories";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse, mockWorkbook } from "./shared";
import { latestValues, mockApplications } from "./subsidy-applications";

/**
 * SUBS-009 … SUBS-011 · The subsidy reports, worked out from the mock's applications with the
 * backend's rules: each ageing figure runs from a recorded start to its end, or to today (or
 * the day it was cancelled) while it has none; supplied means stage 7's supply date is in.
 */

/** figure → (start field, end field); `@full_fp` is the application's own closing date. */
const FIGURES: Readonly<Record<AgeingFigureKey, readonly [string, string]>> = {
  today_to_supply: ["supply", "@full_fp"],
  inward_to_submission: ["app_inward", "submission"],
  wo_to_tpa_received: ["wo_received", "tpa_received"],
  tpa_cleared_to_inspection_sent: ["tpa_cleared", "inspection_sent"],
  inspection_sent_to_tr: ["inspection_sent", "tr_date"],
  fp_submitted_to_full_fp: ["fp_submitted", "@full_fp"],
};

const STATUSES = ["open", "full_fp_received", "cancelled"] as const;
const DEFAULT_AGEING_LIMIT = 50;

function mayView(): boolean {
  return can(mockPermissionsFor(readMockRole()), "subsidy", "view");
}

function days(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000);
}

function districtOf(application: ApplicationWire): string | null {
  return (
    mockTerritoryLineage(application.territory.id).find((item) => item.level === "district")
      ?.name ?? (application.territory.level === "district" ? application.territory.name : null)
  );
}

function ageRow(application: ApplicationWire): AgeRowWire {
  const values = latestValues(application.id);
  const today = todayInIndia();
  // A cancelled application stops counting the day it was cancelled; the mock has no event
  // date at hand, so it uses the current stage's date.
  const stopped = application.status === "cancelled" ? application.current_stage.since : null;
  const figure = (key: AgeingFigureKey): AgeRowWire[AgeingFigureKey] => {
    const [startKey, endKey] = FIGURES[key];
    const start = values[startKey] ?? null;
    const end = endKey === "@full_fp" ? application.full_fp_received_on : (values[endKey] ?? null);
    if (start === null) return { days: null, running: false, since: null, until: end };
    if (end !== null) return { days: days(start, end), running: false, since: start, until: end };
    return {
      days: days(start, stopped ?? today),
      running: stopped === null,
      since: start,
      until: null,
    };
  };
  return {
    application: {
      id: application.id,
      application_no: application.application_no,
      reg_no: application.reg_no,
      farmer_name: application.farmer_name,
      status: application.status,
      stage: application.current_stage.name,
      district: districtOf(application),
    },
    today_to_supply: figure("today_to_supply"),
    inward_to_submission: figure("inward_to_submission"),
    wo_to_tpa_received: figure("wo_to_tpa_received"),
    tpa_cleared_to_inspection_sent: figure("tpa_cleared_to_inspection_sent"),
    inspection_sent_to_tr: figure("inspection_sent_to_tr"),
    fp_submitted_to_full_fp: figure("fp_submitted_to_full_fp"),
  };
}

function readStatus(url: URL): (typeof STATUSES)[number] | null | "bad" {
  const status = url.searchParams.get("status");
  if (status === null) return null;
  return STATUSES.find((item) => item === status) ?? "bad";
}

function money(values: readonly string[]): string {
  return values.reduce((sum, value) => sum + Number(value), 0).toFixed(2);
}

function ageingRows(url: URL): ApplicationWire[] | Response {
  const status = readStatus(url);
  if (status === "bad") {
    return errorResponse(422, "validation_error", "Some fields need correcting.", {
      status: "open, full_fp_received or cancelled",
    });
  }
  const stage = url.searchParams.get("stage");
  const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
  return mockApplications().filter(
    (row) =>
      (status === null || row.status === status) &&
      (stage === null || row.current_stage.code === stage) &&
      (q === "" ||
        row.application_no.toLowerCase().includes(q) ||
        (row.reg_no ?? "").toLowerCase().includes(q) ||
        row.farmer_name.toLowerCase().includes(q)),
  );
}

function stageRows(status: (typeof STATUSES)[number]): StageRowWire[] {
  const today = todayInIndia();
  return MOCK_STAGE_DEFS.flatMap((stage) => {
    const here = mockApplications().filter(
      (row) => row.current_stage.code === stage.code && row.status === status,
    );
    if (here.length === 0) return [];
    return [
      {
        seq: stage.seq,
        code: stage.code,
        name: stage.name,
        count: here.length,
        total_cost: money(here.map((row) => row.figures.total_cost)),
        subsidy: money(here.map((row) => row.figures.subsidy)),
        farmer_share: money(here.map((row) => row.figures.farmer_share)),
        oldest_days_in_stage: Math.max(...here.map((row) => days(row.current_stage.since, today))),
      },
    ];
  });
}

function supplyRows(status: (typeof STATUSES)[number] | null): SupplyRowWire[] {
  const rows = mockApplications().filter((row) =>
    status === null ? row.status !== "cancelled" : row.status === status,
  );
  const byDistrict = new Map<string, ApplicationWire[]>();
  for (const row of rows) {
    const district = districtOf(row) ?? "(no district)";
    byDistrict.set(district, [...(byDistrict.get(district) ?? []), row]);
  }
  return [...byDistrict.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([district, list]) => {
      const supplied = list.filter((row) => (latestValues(row.id).supply ?? null) !== null);
      const notSupplied = list.filter((row) => !supplied.includes(row));
      return {
        district,
        supplied: supplied.length,
        not_supplied: notSupplied.length,
        supplied_cost: money(supplied.map((row) => row.figures.total_cost)),
        not_supplied_cost: money(notSupplied.map((row) => row.figures.total_cost)),
      };
    });
}

const FIGURE_HEADERS = AGEING_FIGURES.map((key) => key.replaceAll("_", " "));

export const subsidyReportHandlers = [
  http.get(buildApiUrl("/subsidy-reports/ageing/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "Not permitted.");
    const rows = ageingRows(new URL(request.url));
    if (rows instanceof Response) return rows;
    return mockWorkbook(
      "subsidy-ageing",
      ["Application No.", "Farmer", "Stage", ...FIGURE_HEADERS],
      rows.map((row) => {
        const age = ageRow(row);
        return [
          row.application_no,
          row.farmer_name,
          row.current_stage.name,
          ...AGEING_FIGURES.map((key) => String(age[key].days ?? "")),
        ];
      }),
    );
  }),

  http.get(buildApiUrl("/subsidy-reports/ageing"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "Not permitted.");
    const url = new URL(request.url);
    const rows = ageingRows(url);
    if (rows instanceof Response) return rows;
    const all = scenario === "empty" ? [] : rows;
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? DEFAULT_AGEING_LIMIT);
    return HttpResponse.json({
      data: all.slice(offset, offset + limit).map(ageRow),
      meta: {
        limit,
        next_cursor: offset + limit < all.length ? encodeCursor(offset + limit) : null,
      },
    });
  }),

  http.get(buildApiUrl("/subsidy-reports/stages/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "Not permitted.");
    const status = readStatus(new URL(request.url));
    const rows = stageRows(status === null || status === "bad" ? "open" : status);
    return mockWorkbook(
      "subsidy-stages",
      ["Stage", "Applications", "Total cost", "Subsidy", "Farmer share", "Oldest (days)"],
      rows.map((row) => [
        `${String(row.seq)}. ${row.name}`,
        String(row.count),
        row.total_cost,
        row.subsidy,
        row.farmer_share,
        String(row.oldest_days_in_stage ?? ""),
      ]),
    );
  }),

  http.get(buildApiUrl("/subsidy-reports/stages"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "Not permitted.");
    const status = readStatus(new URL(request.url));
    if (status === "bad") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        status: "open, full_fp_received or cancelled",
      });
    }
    const rows = scenario === "empty" ? [] : stageRows(status ?? "open");
    return HttpResponse.json({ data: rows, meta: { limit: rows.length, next_cursor: null } });
  }),

  http.get(buildApiUrl("/subsidy-reports/supply/export"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "Not permitted.");
    const status = readStatus(new URL(request.url));
    return mockWorkbook(
      "subsidy-supply",
      ["District", "Supplied", "Not supplied", "Supplied cost", "Not supplied cost"],
      supplyRows(status === "bad" ? null : status).map((row) => [
        row.district,
        String(row.supplied),
        String(row.not_supplied),
        row.supplied_cost,
        row.not_supplied_cost,
      ]),
    );
  }),

  http.get(buildApiUrl("/subsidy-reports/supply"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "Not permitted.");
    const status = readStatus(new URL(request.url));
    if (status === "bad") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        status: "open, full_fp_received or cancelled",
      });
    }
    const rows = scenario === "empty" ? [] : supplyRows(status);
    return HttpResponse.json({ data: rows, meta: { limit: rows.length, next_cursor: null } });
  }),
];
