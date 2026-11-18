import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { server } from "@/mocks/node";

import { getDashboardOverview } from "./dashboard.api";
import { amount, figure, trendPoints, type DashboardOverviewWire } from "./dashboard.schemas";

/** The backend's answer from backend/docs/api/dashboard.md, snake_case with decimal strings. */
const BACKEND_ANSWER: DashboardOverviewWire = {
  period_label: "Last 30 days",
  period: { start: "2026-09-02", end: "2026-10-01" },
  kpis: {
    pipeline_value: { value: "2485000.00", delta_percent: null, trend: [] },
    new_leads: { value: "42", delta_percent: "12.5", trend: ["8", "11", "9", "14"] },
    conversion_rate: { value: "18.4", delta_percent: "-2.1", trend: ["20.0", "18.4"] },
    overdue_follow_ups: { value: null, delta_percent: null, trend: [] },
  },
  pipeline: [
    { stage: "new", count: 12, value: "450000.00" },
    { stage: "dormant", count: 1, value: "0.00" },
  ],
  sources: [{ source: "field_visit", name: "Field visit", count: 30 }],
  area_by_system: [{ system: "drip", name: "Drip", leads: 14, hectares: "38.50" }],
  targets_by_month: [
    { month: "2026-09", target: "1200000.00", achieved: "984000.00" },
    { month: "2026-10", target: "0.00", achieved: null },
  ],
  follow_ups: [
    {
      task_id: "task-1",
      lead_id: "lead-1",
      farmer_name: "Ramesh Patel",
      district: null,
      due_at: "2026-09-30T04:30:00Z",
      assigned_to: { id: "u-1", full_name: "" },
      overdue: true,
    },
  ],
};

describe("[RPT-001] getDashboardOverview", () => {
  afterEach(() => {
    writeMockRole("state_manager");
  });

  it("reads the backend's shape, keeping money as strings", async () => {
    server.use(
      http.get(buildApiUrl("/dashboard/overview"), () =>
        HttpResponse.json({ data: BACKEND_ANSWER }),
      ),
    );

    const overview = await getDashboardOverview();

    expect(overview.kpis.pipelineValue).toEqual({
      value: "2485000.00",
      deltaPercent: null,
      trend: [],
    });
    expect(overview.kpis.overdueFollowUps.value).toBeNull();
    expect(overview.pipeline.map((stage) => stage.stage)).toEqual(["new", "dormant"]);
    expect(overview.areaBySystem).toEqual([
      { system: "drip", name: "Drip", leads: 14, hectares: "38.50" },
    ]);
    expect(overview.targetsByMonth).toEqual([
      { month: "2026-09", target: "1200000.00", achieved: "984000.00" },
      { month: "2026-10", target: "0.00", achieved: null },
    ]);
    expect(overview.followUps[0]).toEqual({
      taskId: "task-1",
      leadId: "lead-1",
      customerName: "Ramesh Patel",
      district: null,
      dueAt: "2026-09-30T04:30:00Z",
      ownerName: null,
      overdue: true,
    });
  });

  it("reads a backend from before FS-052 as no areas and no targets", async () => {
    const { area_by_system: _area, targets_by_month: _targets, ...older } = BACKEND_ANSWER;
    server.use(
      http.get(buildApiUrl("/dashboard/overview"), () => HttpResponse.json({ data: older })),
    );

    const overview = await getDashboardOverview();

    expect(overview.areaBySystem).toEqual([]);
    expect(overview.targetsByMonth).toBeNull();
  });

  it("refuses a month that is not YYYY-MM as a contract violation", async () => {
    server.use(
      http.get(buildApiUrl("/dashboard/overview"), () =>
        HttpResponse.json({
          data: {
            ...BACKEND_ANSWER,
            targets_by_month: [{ month: "Oct 2026", target: "0.00", achieved: null }],
          },
        }),
      ),
    );

    await expect(getDashboardOverview()).rejects.toSatisfy(
      (error) => isApiError(error) && error.kind === "contract",
    );
  });

  it("refuses the old camelCase shape as a contract violation", async () => {
    server.use(
      http.get(buildApiUrl("/dashboard/overview"), () =>
        HttpResponse.json({ periodLabel: "Last 30 days", kpis: {} }),
      ),
    );

    await expect(getDashboardOverview()).rejects.toSatisfy(
      (error) => isApiError(error) && error.kind === "contract",
    );
  });

  it("reads the mock backend, which answers in the same shape", async () => {
    const overview = await getDashboardOverview();
    expect(overview.pipeline.length).toBeGreaterThan(0);
    expect(typeof overview.kpis.pipelineValue.value).toBe("string");
    expect(overview.areaBySystem.length).toBeGreaterThan(0);
    expect(overview.targetsByMonth).toHaveLength(6);
  });

  it("sends the mock's targets only to a role with a targets permission, as the backend does", async () => {
    writeMockRole("account_manager");
    const overview = await getDashboardOverview();
    expect(overview.targetsByMonth).toBeNull();
  });
});

describe("[RPT-001] dashboard figures", () => {
  it("turns counts and percentages into numbers only for display and drawing", () => {
    expect(figure("18.4")).toBe(18.4);
    expect(figure(null)).toBeNull();
    expect(figure("n/a")).toBeNull();
    expect(trendPoints(["8", "11", "x"])).toEqual([8, 11]);
    expect(amount("38.50")).toBe(38.5);
    expect(amount(null)).toBe(0);
  });
});
