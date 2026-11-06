import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { getLead, reopenLead, transitionLead } from "@/features/leads/api/leads.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { mockLookupRows } from "@/mocks/data/lookups";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadDetail } from "./lead-detail";

function dormantLead(): (typeof mockDb.leads)[number] {
  const lead = mockDb.leads.find((item) => item.stage === "dormant");
  if (lead === undefined) throw new Error("No dormant lead in the mock database");
  return lead;
}

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

describe("[LEAD-007] Dormant leads, through the API", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("reads the stage a dormant lead returns to", async () => {
    const lead = await getLead(dormantLead().id);
    expect(lead).toMatchObject({ stage: "dormant", dormantFromStage: "qualified" });
  });

  it("reopens a dormant lead to where it stood, without counting a reopen", async () => {
    const seeded = dormantLead();
    const before = seeded.reopen_count;

    const lead = await reopenLead({
      leadId: seeded.id,
      body: { note: "Farmer called back" },
      idempotencyKey: "d-1",
    });

    expect(lead).toMatchObject({ stage: "qualified", dormantFromStage: null, reopenCount: before });
  });

  it("closes a dormant lead as lost; reopened, it goes back to where it went dormant", async () => {
    const seeded = dormantLead();
    const reason = mockLookupRows("lost-reasons")[0];
    if (reason === undefined) throw new Error("No lost reason");

    const lost = await transitionLead({
      leadId: seeded.id,
      body: {
        to_stage: "lost",
        expected_stage: "dormant",
        lost_reason_id: reason.id,
        lost_note: null,
      },
      idempotencyKey: "d-2",
    });
    expect(lost.stage).toBe("lost");

    const reopened = await reopenLead({
      leadId: seeded.id,
      body: { note: null },
      idempotencyKey: "d-3",
    });
    expect(reopened.stage).toBe("qualified");
  });
});

describe("[LEAD-007] A dormant lead's page", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("says it is dormant and where it was, and offers reopen or lost", async () => {
    signInAs("employee");
    const user = showLead(dormantLead().id);

    expect(await screen.findByText("Dormant: no activity for a long time")).toBeInTheDocument();
    expect(screen.getByText(/It was Qualified\./)).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Update stage" }));
    const menu = await screen.findByRole("menu");
    expect(
      within(menu).getByRole("menuitem", { name: "Reopen lead…" }),
    ).toHaveAccessibleDescription("Back to the stage it was at before.");
    expect(within(menu).getByRole("menuitem", { name: "Mark as lost…" })).toBeInTheDocument();
  });

  it("reopens it back to Qualified", async () => {
    signInAs("employee");
    const lead = dormantLead();
    const user = showLead(lead.id);

    await user.click(await screen.findByRole("button", { name: "Update stage" }));
    await user.click(await screen.findByRole("menuitem", { name: "Reopen lead…" }));
    const dialog = await screen.findByRole("dialog", { name: "Reopen lead" });
    expect(within(dialog).getByText(/goes back to Qualified, where it was before/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Reopen lead" }));

    expect(await screen.findByText("Lead reopened")).toBeInTheDocument();
    expect(lead.stage).toBe("qualified");
    expect(screen.queryByText("Dormant: no activity for a long time")).not.toBeInTheDocument();
  });
});
