import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { downloadReport, getLead360, getReport } from "@/features/reports/api/reports.api";
import type { ReportParams } from "@/features/reports/api/reports.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { Lead360Card } from "./lead-360";
import { ReportView } from "./report-view";
import { ReportsHome } from "./reports-home";

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

function show(ui: React.JSX.Element, searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(ui, { searchParams });
  return user;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[RPT-002] Reports, through the API", () => {
  afterEach(reset);

  it("counts leads created in the window, grouped as asked", async () => {
    signInAs("state_manager");
    const bySource = await getReport("lead-conversion", DEFAULTS);
    expect(bySource.rows.length).toBeGreaterThan(0);
    expect(bySource.totals.leads).toBe(bySource.rows.reduce((sum, row) => sum + row.leads, 0));
    expect(bySource.filters).toMatchObject({ from: shiftCalendarDay(todayInIndia(), -29) });

    const byOwner = await getReport("lead-conversion", { ...DEFAULTS, groupBy: "owner" });
    expect(byOwner.totals.leads).toBe(bySource.totals.leads);

    await expect(
      getReport("lead-conversion", { ...DEFAULTS, groupBy: "colour" }),
    ).rejects.toMatchObject({ status: 422 });
    await expect(
      getReport("lead-conversion", { ...DEFAULTS, from: "2026-10-10", to: "2026-10-01" }),
    ).rejects.toMatchObject({ status: 422 });
  });

  it("sends null for a figure the role may not see, never 0", async () => {
    signInAs("state_manager");
    const people = await getReport("salesperson-performance", DEFAULTS);
    expect(people.rows[0]?.visits).toBeNull();
    expect(people.rows[0]?.leadsCreated).toEqual(expect.any(Number));

    signInAs("admin");
    const seen = await getReport("salesperson-performance", DEFAULTS);
    expect(seen.rows[0]?.visits).toEqual(expect.any(Number));
  });

  it("refuses a report the role may not run, and downloads one it may", async () => {
    signInAs("employee");
    await expect(getReport("complaints", DEFAULTS)).rejects.toMatchObject({ status: 403 });

    signInAs("qa_manager");
    await expect(getReport("lead-conversion", DEFAULTS)).rejects.toMatchObject({ status: 403 });

    signInAs("district_manager");
    const file = await downloadReport("lost-leads", { ...DEFAULTS, groupBy: "owner" });
    expect(file.filename).toMatch(/^report-lost-leads-\d{4}-\d{2}-\d{2}\.xlsx$/);
  });

  it("[RPT-003] gives a lead's tiles and the leads on its mobile", async () => {
    signInAs("admin");
    const lead = mockDb.leads[0];
    if (lead === undefined) throw new Error("no seeded lead");
    const twin = mockDb.leads[1];
    if (twin === undefined) throw new Error("no second lead");
    twin.mobile = lead.mobile;

    const view = await getLead360(lead.id);
    expect(view.relatedLeads.map((item) => item.id)).toContain(twin.id);
    expect(view.summary.quotations).toEqual(expect.any(Number));

    signInAs("employee");
    await expect(getLead360(lead.id)).rejects.toMatchObject({ status: 403 });
  });
});

describe("[RPT-002] ReportsHome", () => {
  afterEach(reset);

  it("shows a card per report the role may open, with its figure", async () => {
    signInAs("district_manager");
    show(<ReportsHome />);

    expect(await screen.findByRole("link", { name: "Lead conversion" })).toHaveAttribute(
      "href",
      "/reports/lead-conversion",
    );
    expect(await screen.findByText(/% converted$/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Complaints" })).toBeInTheDocument();
  });

  it("hides the reports a role may not run", async () => {
    signInAs("employee");
    show(<ReportsHome />);
    expect(await screen.findByText("No reports for your role")).toBeInTheDocument();
  });
});

describe("[RPT-002] ReportView", () => {
  afterEach(reset);

  it("shows a report's table and totals, regrouped from the By filter", async () => {
    signInAs("admin");
    const user = show(<ReportView name="lead-conversion" />);

    const table = await screen.findByRole("table", { name: "Lead conversion by source" });
    expect(within(table).getByRole("rowheader", { name: "Total" })).toBeInTheDocument();
    expect(screen.getByText(/to .*\.$/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /By/ }));
    await user.click(await screen.findByRole("radio", { name: "Person" }));
    expect(
      await screen.findByRole("table", { name: "Lead conversion by person" }),
    ).toBeInTheDocument();
  });

  it("marks figures the role doesn't see, and the sale setting they used", async () => {
    signInAs("state_manager");
    show(<ReportView name="salesperson-performance" />);

    expect(
      await screen.findByRole("table", { name: "Salesperson performance" }),
    ).toBeInTheDocument();
    expect(screen.getByText("A dash is a figure your role doesn't see.")).toBeInTheDocument();
    expect(screen.getAllByText("Not available to you").length).toBeGreaterThan(0);
    expect(screen.getByText(/Sales counted at: approval\./)).toBeInTheDocument();
  });

  it("refuses a window over a year before asking", async () => {
    signInAs("admin");
    show(<ReportView name="lost-leads" />, "?from=2024-01-01&to=2026-10-01");
    expect(
      await screen.findByText("A report covers a year at most. Shorten the window."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("says when the role may not run the report", async () => {
    signInAs("employee");
    show(<ReportView name="follow-ups" />);
    expect(await screen.findByText("You can't run this report")).toBeInTheDocument();
  });
});

describe("[RPT-003] Lead360Card", () => {
  afterEach(reset);

  it("shows the tiles and the leads on the same mobile", async () => {
    signInAs("state_manager");
    const lead = mockDb.leads[0];
    const twin = mockDb.leads[1];
    if (lead === undefined || twin === undefined) throw new Error("no seeded leads");
    twin.mobile = lead.mobile;
    show(<Lead360Card leadId={lead.id} />);

    expect(await screen.findByText("Same mobile (1)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: twin.inquiry_no })).toHaveAttribute(
      "href",
      `/leads/${twin.id}`,
    );
    expect(screen.getByText("Quotations")).toBeInTheDocument();
    // Payments are not the State Manager's in the mock: the figure is withheld.
    await waitFor(() => {
      expect(screen.getAllByText("Not available to you").length).toBeGreaterThan(0);
    });
  });

  it("shows nothing to a role without reports", async () => {
    signInAs("employee");
    const lead = mockDb.leads[0];
    if (lead === undefined) throw new Error("no seeded lead");
    const { container } = renderWithProviders(<Lead360Card leadId={lead.id} />);
    await waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });
});
