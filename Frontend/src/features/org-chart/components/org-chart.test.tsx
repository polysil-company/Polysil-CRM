import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { getOrgChart } from "@/features/org-chart/api/org-chart.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { OrgChartView } from "./org-chart-view";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function idOf(name: string): string {
  const user = mockDb.users.find((item) => item.full_name === name);
  if (user === undefined) throw new Error(`No ${name}`);
  return user.id;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[ADMN-008] The org chart, through the API", () => {
  afterEach(reset);

  it("gives a field officer their line, nearest manager first", async () => {
    signInAs("employee");
    const chart = await getOrgChart({ userId: null, company: false });
    expect(chart.subject?.name).toBe("Ravi Joshi");
    expect(chart.managers.map((step) => step.map((person) => person.name))).toEqual([
      ["Nirav Shah"],
      ["Asha Patel"],
    ]);
    expect(chart.people).toEqual([]);
  });

  it("gives a manager everyone below, counted by role, and the picture of someone below", async () => {
    signInAs("state_manager");
    const mine = await getOrgChart({ userId: null, company: false });
    expect(mine.total).toBe(4);
    expect(mine.byRole).toEqual([
      { roleName: "District Manager", count: 1 },
      { roleName: "Field Officer", count: 3 },
    ]);
    const theirs = await getOrgChart({ userId: idOf("Nirav Shah"), company: false });
    expect(theirs.people.map((person) => person.name)).toEqual(["Ravi Joshi"]);
  });

  it("shows nobody above, and the whole company only to someone who sees every user", async () => {
    signInAs("district_manager");
    await expect(getOrgChart({ userId: idOf("Asha Patel"), company: false })).rejects.toMatchObject(
      { status: 404 },
    );
    await expect(getOrgChart({ userId: null, company: true })).rejects.toMatchObject({
      status: 403,
    });
    signInAs("admin");
    const company = await getOrgChart({ userId: null, company: true });
    expect(company.subject).toBeNull();
    expect(company.total).toBeGreaterThan(4);
  });
});

describe("[ADMN-008] OrgChartView", () => {
  afterEach(reset);

  it("shows a manager's team as a tree, each team folding away", async () => {
    signInAs("state_manager");
    const user = userEvent.setup();
    renderWithProviders(<OrgChartView />);

    expect(await screen.findByRole("heading", { name: "Your team" })).toBeInTheDocument();
    expect(screen.getByText("4 people below.")).toBeInTheDocument();
    const team = screen.getByRole("list", { name: "Team" });
    expect(within(team).getByRole("link", { name: "Ravi Joshi" })).toBeInTheDocument();
    await user.click(within(team).getByRole("button", { name: "Hide Nirav Shah's team" }));
    expect(within(team).queryByRole("link", { name: "Ravi Joshi" })).not.toBeInTheDocument();
    expect(within(team).getByRole("link", { name: "Nirav Shah" })).toHaveAttribute(
      "href",
      `/org-chart?user=${idOf("Nirav Shah")}`,
    );
  });

  it("shows a field officer whom they report to", async () => {
    signInAs("employee");
    renderWithProviders(<OrgChartView />);

    const line = await screen.findByRole("list", { name: "Reports to" });
    expect(
      within(line)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([expect.stringContaining("Nirav Shah"), expect.stringContaining("Asha Patel")]);
    expect(screen.getByText("Nobody reports to you.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Whole company" })).not.toBeInTheDocument();
  });

  it("says when someone isn't below you", async () => {
    signInAs("district_manager");
    renderWithProviders(<OrgChartView />, { searchParams: `?user=${idOf("Asha Patel")}` });
    expect(await screen.findByText("No reporting line to show")).toBeInTheDocument();
  });

  it("opens the whole company for someone who sees every user", async () => {
    signInAs("admin");
    renderWithProviders(<OrgChartView />, { searchParams: "?view=company" });
    expect(await screen.findByRole("heading", { name: "The whole company" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Whole company" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
