import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { SubsidyReports } from "./subsidy-reports";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

describe("[SUBS-010] SubsidyReports", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("opens on the stage report of open applications, with a total row", async () => {
    signInAs("state_manager");
    renderWithProviders(<SubsidyReports />);
    const table = await screen.findByRole("table", { name: "Open applications by stage" });
    expect(within(table).getByRole("rowheader", { name: "All stages" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Oldest" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download Excel/ })).toBeInTheDocument();
  });

  it("[SUBS-011] shows supply by district", async () => {
    signInAs("state_manager");
    const user = userEvent.setup();
    renderWithProviders(<SubsidyReports />);
    await user.click(await screen.findByRole("tab", { name: "Supply" }));
    const table = await screen.findByRole("table", {
      name: "Supplied and not supplied, by district",
    });
    expect(within(table).getByRole("rowheader", { name: "All districts" })).toBeInTheDocument();
  });

  it("[SUBS-009] lists each application's six ageing figures", async () => {
    signInAs("state_manager");
    const user = userEvent.setup();
    renderWithProviders(<SubsidyReports />);
    await user.click(await screen.findByRole("tab", { name: "Ageing" }));
    const list = await screen.findByRole("list", { name: "Ageing by application" });
    const first = within(list).getAllByRole("listitem")[0];
    if (first === undefined) throw new Error("No row");
    expect(within(first).getByText("Inward to submission")).toBeInTheDocument();
    expect(within(first).getByText("FP submitted to full payment")).toBeInTheDocument();
    expect(within(list).getAllByText("running").length).toBeGreaterThan(0);
  });
});
