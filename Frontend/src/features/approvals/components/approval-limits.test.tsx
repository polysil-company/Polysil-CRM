import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ApprovalLimits } from "./approval-limits";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

describe("[APPR-002] ApprovalLimits", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
  });

  it("shows the three ladders (orders, discounts, refunds), read-only to a manager", async () => {
    signInAs("state_manager");
    renderWithProviders(<ApprovalLimits />);

    const orders = await screen.findByRole("list", { name: "Order value, company-wide" });
    expect(within(orders).getByText("Up to ₹1,00,000")).toBeInTheDocument();
    expect(within(orders).getByText("No limit")).toBeInTheDocument();
    const discounts = screen.getByRole("list", { name: "Discount on a quotation, company-wide" });
    expect(within(discounts).getByText("Field officer")).toBeInTheDocument();
    const refunds = screen.getByRole("list", { name: "Refund on a complaint, company-wide" });
    expect(within(refunds).getByText("Up to ₹25,000")).toBeInTheDocument();
    expect(screen.getByText(/Only an administrator changes these/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Change the/ })).not.toBeInTheDocument();
  });

  it("lets an administrator change a limit, refusing one out of order first", async () => {
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <ApprovalLimits />
        <Toaster />
      </>,
    );

    await user.click(
      await screen.findByRole("button", {
        name: "Change the State Manager limit (Order value, company-wide)",
      }),
    );
    const dialog = await screen.findByRole("dialog", { name: "State Manager's order limit" });
    expect(within(dialog).getByText(/Above ₹1,00,000/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument();

    const amount = within(dialog).getByLabelText("Limit in rupees");
    await user.clear(amount);
    await user.type(amount, "50000");
    await user.click(within(dialog).getByRole("button", { name: "Save limit" }));
    expect(
      await within(dialog).findByText("Must be above ₹1,00,000, the level below"),
    ).toBeInTheDocument();

    await user.clear(amount);
    await user.type(amount, "400000");
    await user.click(within(dialog).getByRole("button", { name: "Save limit" }));
    expect(await screen.findByText("State Manager's order limit changed")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        within(screen.getByRole("list", { name: "Order value, company-wide" })).getByText(
          "Up to ₹4,00,000",
        ),
      ).toBeInTheDocument();
    });
  });
});
