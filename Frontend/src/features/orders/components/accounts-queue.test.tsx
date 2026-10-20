import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole, writeMockScenario } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { AccountsQueue } from "./accounts-queue";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
  writeMockScenario("realistic");
}

describe("[ACCT-001] AccountsQueue", () => {
  afterEach(reset);

  it("lists the orders waiting on Accounts' payment check, each sent to Approvals", async () => {
    signInAs("account_manager");
    renderWithProviders(<AccountsQueue />);

    const list = await screen.findByRole("list", { name: "Orders waiting on Accounts" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(1);
    expect(screen.getByText("1 order waits on Accounts' payment check.")).toBeInTheDocument();
    const row = rows[0];
    if (row === undefined) throw new Error("No row");
    expect(within(row).getByRole("link", { name: /^SO\// })).toHaveAttribute(
      "href",
      expect.stringMatching(/^\/sales-orders\//),
    );
    expect(
      await within(row).findByRole("link", { name: /^Decide .* in Approvals$/ }),
    ).toHaveAttribute("href", "/approvals");
    expect(screen.getByRole("button", { name: "Download Excel" })).toBeInTheDocument();
  });

  it("says when nothing waits on Accounts", async () => {
    signInAs("account_manager");
    writeMockScenario("empty");
    renderWithProviders(<AccountsQueue />);

    expect(await screen.findByText("Nothing waits on Accounts")).toBeInTheDocument();
    expect(
      screen.getByText(/once its managers have approved it and the payment check is next/),
    ).toBeInTheDocument();
  });
});
