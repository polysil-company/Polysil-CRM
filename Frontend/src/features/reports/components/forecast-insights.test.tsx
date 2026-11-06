import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { getReport } from "@/features/reports/api/reports.api";
import type { ReportParams } from "@/features/reports/api/reports.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ReportView } from "./report-view";

const DEFAULTS: ReportParams = {
  from: null,
  to: null,
  territories: [],
  owner: null,
  groupBy: null,
};

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

const THIN_FORECAST = {
  data: {
    group_by: "owner",
    months: ["2026-11", "2026-12", "2027-01"],
    rows: [
      {
        key: { id: "u1", label: "Ravi Joshi" },
        open: 4,
        with_value: 3,
        pipeline_value: "480000.00",
        weighted_value: null,
        by_month: { "2026-11": null, "2026-12": null, "2027-01": null, later: null },
        valued_by: { quotation: 1, estimate: 2 },
      },
    ],
    truncated: false,
    row_count: 1,
    rates: [],
    median_days_to_win: null,
    reason: "not_enough_history",
    filters: { history_days: 180, as_of: "2026-11-05", rates_from: "your_whole_scope" },
    totals: {
      open: 4,
      with_value: 3,
      pipeline_value: "480000.00",
      weighted_value: null,
      by_month: { "2026-11": null, "2026-12": null, "2027-01": null, later: null },
      valued_by: { quotation: 1, estimate: 2 },
    },
  },
};

describe("[RPT-004] The sales forecast (FS-079)", () => {
  afterEach(reset);

  it("weighs the open pipeline by month, with the rates it used", async () => {
    signInAs("state_manager");
    const forecast = await getReport("sales-forecast", DEFAULTS);
    expect(forecast.months).toHaveLength(3);
    expect(forecast.totals.open).toBe(forecast.rows.reduce((sum, row) => sum + row.open, 0));
    expect(forecast.rates.length).toBeGreaterThan(0);
    const byTerritory = await getReport("sales-forecast", { ...DEFAULTS, groupBy: "territory" });
    expect(byTerritory.totals.open).toBe(forecast.totals.open);
  });

  it("shows the table, the likely total and the win rates", async () => {
    signInAs("state_manager");
    renderWithProviders(<ReportView name="sales-forecast" />);

    expect(
      await screen.findByRole("table", { name: "Sales forecast by person" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Likely", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Win rates used" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Later" })).toBeInTheDocument();
  });

  it("says when there's too little history, and shows dashes rather than zeros", async () => {
    signInAs("state_manager");
    server.use(
      http.get(buildApiUrl("/reports/sales-forecast"), () => HttpResponse.json(THIN_FORECAST)),
    );
    renderWithProviders(<ReportView name="sales-forecast" />);

    expect(
      await screen.findByText("Not enough won or lost leads to weigh the pipeline yet"),
    ).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Sales forecast by person" });
    const ravi = within(table).getByRole("row", { name: /Ravi Joshi/ });
    expect(within(ravi).getAllByText("—").length).toBeGreaterThan(0);
    expect(within(ravi).queryByText("₹0")).not.toBeInTheDocument();
  });
});

describe("[RPT-005] Insights (FS-079)", () => {
  afterEach(reset);

  it("reads each sentence with its figure, and links the report behind it", async () => {
    signInAs("state_manager");
    server.use(
      http.get(buildApiUrl("/reports/insights"), () =>
        HttpResponse.json({
          data: {
            rows: [
              {
                code: "lost_reason_rising",
                title: "“Price too high” grew most among lost leads.",
                figure: "42.5",
                previous: "30.0",
                unit: "pct",
                link: { report: "lost-leads", group_by: "reason" },
              },
              {
                code: "first_contact_speed",
                title: "New leads were first contacted in about this long.",
                figure: "6",
                previous: null,
                unit: "hours",
                link: null,
              },
            ],
            truncated: false,
            row_count: 2,
            filters: {
              from: "2026-10-07",
              to: "2026-11-05",
              previous_from: "2026-09-07",
              previous_to: "2026-10-06",
            },
          },
        }),
      ),
    );
    renderWithProviders(<ReportView name="insights" />);

    const list = await screen.findByRole("list", { name: "Insights" });
    expect(within(list).getByText(/Price too high/)).toBeInTheDocument();
    expect(within(list).getByText(/was 30(\.0)?% before/)).toBeInTheDocument();
    expect(within(list).getByText("6 hours")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "See the report" })).toHaveAttribute(
      "href",
      "/reports/lost-leads?by=reason",
    );
  });

  it("says too little happened, rather than nothing is wrong", async () => {
    signInAs("state_manager");
    server.use(
      http.get(buildApiUrl("/reports/insights"), () =>
        HttpResponse.json({
          data: { rows: [], truncated: false, row_count: 0, filters: {} },
        }),
      ),
    );
    renderWithProviders(<ReportView name="insights" />);
    expect(await screen.findByText(/Too little happened in this window/)).toBeInTheDocument();
  });
});
