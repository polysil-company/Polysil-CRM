import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_STAFF } from "@/mocks/data/reference";
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

/** The session for the screen, and the same role for the mock backend's answers. */
function signInAs(role: Role): void {
  writeMockRole(role);
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

describe("[LEAD-008] LeadAssignDialog", () => {
  afterEach(() => {
    writeMockRole("state_manager");
    resetMockDb();
  });

  it("changes the owner and the partner, and shows them on the lead", async () => {
    signInAs("state_manager");
    const lead = leadAt("contacted");
    const newOwner = MOCK_STAFF.find((person) => person.id !== lead.owner?.id);
    const user = showLead(lead.id);

    await user.click(await screen.findByRole("button", { name: "Assign" }));
    const dialog = await screen.findByRole("dialog", { name: "Assign lead" });
    const save = within(dialog).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();

    const owner = within(dialog).getByRole("combobox", { name: "Owner" });
    await waitFor(() => {
      expect(owner).toBeEnabled();
    });
    await user.clear(owner);
    await user.type(owner, newOwner?.full_name.split(" ")[0] ?? "");
    await user.click(
      await screen.findByRole("option", { name: new RegExp(newOwner?.full_name ?? "") }),
    );

    const partner = within(dialog).getByRole("combobox", { name: "Channel partner" });
    await user.clear(partner);
    await user.type(partner, "Khodiyar");
    await user.click(await screen.findByRole("option", { name: /Khodiyar Irrigation/ }));

    await user.click(save);

    expect(await screen.findByText("Lead assigned")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Assign lead" })).not.toBeInTheDocument();
    });
    expect(await screen.findByText("Khodiyar Irrigation · Dealer")).toBeInTheDocument();
    expect(lead.owner?.id).toBe(newOwner?.id);
    expect(
      await screen.findByText(/changed the owner and the channel partner/),
    ).toBeInTheDocument();
  });

  it("tells someone who may not set owners, and still lets them change the partner", async () => {
    signInAs("employee");
    const lead = leadAt("contacted");
    const user = showLead(lead.id);

    await user.click(await screen.findByRole("button", { name: "Assign" }));
    const dialog = await screen.findByRole("dialog", { name: "Assign lead" });

    expect(
      await within(dialog).findByText(/only a manager can change the owner/),
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole("combobox", { name: "Owner" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("combobox", { name: "Channel partner" })).toBeInTheDocument();
  });

  it("puts a refused partner on the partner field", async () => {
    signInAs("state_manager");
    server.use(
      http.post(buildApiUrl("/leads/:leadId/assign"), () =>
        HttpResponse.json(
          {
            error: {
              code: "validation_error",
              message: "Some fields need correcting.",
              fields: { assigned_partner_id: "not in your scope" },
            },
          },
          { status: 422 },
        ),
      ),
    );
    const user = showLead(leadAt("contacted").id);

    await user.click(await screen.findByRole("button", { name: "Assign" }));
    const dialog = await screen.findByRole("dialog", { name: "Assign lead" });
    const partner = within(dialog).getByRole("combobox", { name: "Channel partner" });
    await user.clear(partner);
    await user.type(partner, "Babra");
    await user.click(await screen.findByRole("option", { name: /Babra Farm Supplies/ }));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    expect(await within(dialog).findByText("This partner isn't in your area")).toBeInTheDocument();
    expect(partner).toHaveAttribute("aria-invalid", "true");
  });

  it("offers no reassignment on a closed lead", async () => {
    signInAs("state_manager");
    showLead(leadAt("won").id);

    expect(await screen.findByRole("heading", { name: "Details" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign" })).not.toBeInTheDocument();
  });
});
