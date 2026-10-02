import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { server } from "@/mocks/node";

import { getDashboardOverview } from "./dashboard.api";
import { figure, trendPoints, type DashboardOverviewWire } from "./dashboard.schemas";

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
  });
});

describe("[RPT-001] dashboard figures", () => {
  it("turns counts and percentages into numbers only for display and drawing", () => {
    expect(figure("18.4")).toBe(18.4);
    expect(figure(null)).toBeNull();
    expect(figure("n/a")).toBeNull();
    expect(trendPoints(["8", "11", "x"])).toEqual([8, 11]);
  });
});
