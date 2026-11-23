import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { getReport } from "@/features/reports/api/reports.api";
import type { ReportParams } from "@/features/reports/api/reports.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ReportView } from "./report-view";

const DEFAULTS: ReportParams = {
  from: null,
  to: null,
  territories: [],
  owner: null,
  teamOf: null,
  roles: [],
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

function seeded(roleCode: string): { id: string; name: string } {
  const user = mockDb.users.find(
    (item) => item.is_active && item.deleted_at === null && item.role?.code === roleCode,
  );
  if (user === undefined) throw new Error(`No seeded ${roleCode}.`);
  return { id: user.id, name: user.full_name };
}

describe("[RPT-006] Team and role filters on the reports (FS-082)", () => {
  afterEach(reset);

  it("sends the team and the roles, and lists every team member with role and office", async () => {
    signInAs("admin");
    const asked: { params: URLSearchParams | null } = { params: null };
    server.events.on("request:start", ({ request }) => {
      if (request.url.includes("/reports/salesperson-performance")) {
        asked.params = new URL(request.url).searchParams;
      }
    });
    const head = seeded("district_manager");

    const team = await getReport("salesperson-performance", { ...DEFAULTS, teamOf: head.id });
    expect(asked.params?.get("team_of")).toBe(head.id);
    expect(asked.params?.has("owner_id")).toBe(false);
    const named = team.rows.find((row) => row.user.id === head.id);
    expect(named).toMatchObject({ role: "District Manager" });
    expect(named?.office).not.toBeNull();

    const officers = await getReport("salesperson-performance", {
      ...DEFAULTS,
      roles: ["field_officer", "district_manager"],
    });
    expect(asked.params?.get("roles")).toBe("field_officer,district_manager");
    expect(officers.rows.length).toBeGreaterThan(0);
    for (const row of officers.rows) {
      expect(["Field Officer", "District Manager"]).toContain(row.role);
    }
    server.events.removeAllListeners();
  });

  it("passes on a team outside the caller's line", async () => {
    signInAs("admin");
    await expect(
      getReport("lead-conversion", { ...DEFAULTS, teamOf: "00000000-0000-4000-8000-000000000999" }),
    ).rejects.toMatchObject({ status: 404, code: "not_in_your_line" });
  });

  it("picks a team, which drops the one person, and shows each row's role and office", async () => {
    signInAs("admin");
    const head = seeded("state_manager");
    const someone = seeded("field_officer");
    const user = userEvent.setup();
    renderWithProviders(<ReportView name="salesperson-performance" />, {
      searchParams: `owner=${someone.id}`,
    });

    const table = await screen.findByRole("table", { name: "Salesperson performance" });
    expect(within(table).getByText(someone.name)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Team/ }));
    await user.click(await screen.findByRole("radio", { name: head.name }));

    const row = await screen.findByRole("row", { name: new RegExp(head.name) });
    expect(within(row).getByText(/State Manager · /)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Person/ })).toBeInTheDocument();
  });

  it("offers the staff roles, not the partners'", async () => {
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(<ReportView name="lead-conversion" />);

    await user.click(await screen.findByRole("button", { name: /^Roles/ }));
    expect(await screen.findByRole("checkbox", { name: "Field Officer" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Dealer" })).not.toBeInTheDocument();
  });
});
