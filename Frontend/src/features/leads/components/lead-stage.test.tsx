import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadDetail } from "./lead-detail";

function leadAt(stage: LeadStage): (typeof mockDb.leads)[number] {
  const lead = mockDb.leads.find((item) => item.stage === stage && item.merged_into === null);
  if (lead === undefined) {
    throw new Error(`No ${stage} lead in the mock database`);
  }
  return lead;
}

/** Unit tests have no access token, so the session is served directly for one role. */
function signInAs(role: Role): void {
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function showLead(leadId: string): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <LeadDetail leadId={leadId} />
      <Toaster />
    </>,
  );
  return user;
}

async function openStageMenu(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.click(await screen.findByRole("button", { name: "Update stage" }));
  return screen.findByRole("menu");
}

describe("[LEAD-007] LeadStageMenu", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("marks a new lead as contacted straight from the menu", async () => {
    signInAs("employee");
    const lead = leadAt("new");
    const user = showLead(lead.id);

    const menu = await openStageMenu(user);
    expect(within(menu).getByRole("menuitem", { name: "Mark as lost…" })).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: "Mark as contacted" }));

    expect(await screen.findByText("Moved to Contacted")).toBeInTheDocument();
    expect(lead.stage).toBe("contacted");
    expect(await screen.findByText(/moved the lead from New to Contacted/)).toBeInTheDocument();
  });

  it("asks for a reason before marking a lead lost", async () => {
    signInAs("employee");
    const lead = leadAt("contacted");
    const user = showLead(lead.id);

    const menu = await openStageMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "Mark as lost…" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as lost" });

    await user.click(within(dialog).getByRole("button", { name: "Mark as lost" }));
    expect(await within(dialog).findByText("Choose why the lead was lost")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("combobox", { name: "Reason" }));
    await user.click(await screen.findByRole("option", { name: "Competitor" }));
    await user.type(within(dialog).getByRole("textbox", { name: /Note/ }), "Bought elsewhere");
    await user.click(within(dialog).getByRole("button", { name: "Mark as lost" }));

    expect(await screen.findByText("Lead marked as lost")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Mark as lost" })).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/Reason: Competitor/)).toBeInTheDocument();
    expect(lead.stage).toBe("lost");
  });

  it("reopens a lost lead with a note", async () => {
    signInAs("employee");
    const lead = leadAt("lost");
    const user = showLead(lead.id);

    const menu = await openStageMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "Reopen lead…" }));
    const dialog = await screen.findByRole("dialog", { name: "Reopen lead" });
    await user.type(within(dialog).getByRole("textbox"), "Farmer called back");
    await user.click(within(dialog).getByRole("button", { name: "Reopen lead" }));

    expect(await screen.findByText("Lead reopened")).toBeInTheDocument();
    expect(await screen.findByText("Farmer called back")).toBeInTheDocument();
    expect(lead.stage).not.toBe("lost");
    expect(lead.reopen_count).toBeGreaterThan(0);
  });

  it("says so when someone else moved the lead first", async () => {
    signInAs("employee");
    server.use(
      http.post(buildApiUrl("/leads/:leadId/transition"), () =>
        HttpResponse.json(
          {
            error: {
              code: "stage_changed",
              message: "The lead has moved to a different stage since you loaded it.",
              fields: { stage: "qualified" },
            },
          },
          { status: 409 },
        ),
      ),
    );
    const lead = leadAt("new");
    const user = showLead(lead.id);

    const menu = await openStageMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "Mark as contacted" }));

    expect(await screen.findByText("The lead has changed")).toBeInTheDocument();
    expect(
      screen.getByText(/moved this lead to Qualified while you had it open/),
    ).toBeInTheDocument();
  });

  it("explains inside the dialog why a lead cannot be won yet", async () => {
    signInAs("employee");
    const lead = leadAt("quoted");
    const user = showLead(lead.id);

    const menu = await openStageMenu(user);
    expect(within(menu).getByText("Recorded on the quotation")).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: "Mark as won" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as won" });
    await user.click(within(dialog).getByRole("button", { name: "Mark as won" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "A lead is won when a quotation on it is accepted",
    );
    expect(lead.stage).toBe("quoted");
  });

  it("wins a lead whose quotation was accepted", async () => {
    signInAs("employee");
    const lead = leadAt("negotiation");
    const user = showLead(lead.id);

    const menu = await openStageMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "Mark as won" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as won" });
    await user.click(within(dialog).getByRole("button", { name: "Mark as won" }));

    expect(await screen.findByText("Lead won")).toBeInTheDocument();
    // A won lead is closed: the menu goes away.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Update stage" })).not.toBeInTheDocument();
    });
  });

  it("shows no menu on a won lead, or to someone who cannot edit leads", async () => {
    signInAs("employee");
    showLead(leadAt("won").id);
    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Update stage" })).not.toBeInTheDocument();
  });

  it("hides the menu from a role without leads.edit", async () => {
    signInAs("account_manager");
    showLead(leadAt("new").id);
    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Update stage" })).not.toBeInTheDocument();
  });
});
