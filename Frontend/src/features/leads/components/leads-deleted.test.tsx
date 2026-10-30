import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { deleteLead } from "@/features/leads/api/leads.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadsTable } from "./leads-table";
import { LeadsToolbar } from "./leads-toolbar";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
}

function showLeads(
  searchParams = "",
  onUrlChange?: (queryString: string) => void,
): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <LeadsToolbar />
      <LeadsTable />
      <Toaster />
    </>,
    onUrlChange === undefined ? { searchParams } : { searchParams, onUrlChange },
  );
  return user;
}

describe("[LEAD-019] Deleted leads", () => {
  afterEach(reset);

  it("lists the deleted leads for a deleter, without links, and goes back", async () => {
    signInAs("admin");
    const sent: URL[] = [];
    server.use(
      http.get(buildApiUrl("/leads"), ({ request }) => {
        sent.push(new URL(request.url));
      }),
    );
    const onUrlChange = vi.fn<(queryString: string) => void>();
    const user = showLeads("", onUrlChange);
    await screen.findByRole("table", { name: "Leads" });

    await user.click(await screen.findByRole("button", { name: "Deleted leads" }));

    expect(await screen.findByText(/^Deleted leads\./)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/^1–2 of 2$/)).toBeInTheDocument();
    });
    expect(sent.at(-1)?.searchParams.get("deleted")).toBe("true");
    expect(onUrlChange).toHaveBeenLastCalledWith(expect.stringContaining("deleted=true"));
    const table = screen.getByRole("table", { name: "Leads" });
    const first = mockDb.deletedLeads[0];
    expect(within(table).getByText(first?.farmer_name ?? "")).toBeInTheDocument();
    expect(within(table).queryByRole("link")).not.toBeInTheDocument();
    expect(within(table).getAllByRole("button", { name: /^Restore / })).toHaveLength(2);
    // Nothing to add or review while looking at deleted leads.
    expect(screen.queryByRole("button", { name: "New lead" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Possible duplicates" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back to leads" }));
    await waitFor(() => {
      expect(sent.at(-1)?.searchParams.has("deleted")).toBe(false);
    });
    // LEAD-020 · Restore is on deleted leads only.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /^Restore / })).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/^Deleted leads\./)).not.toBeInTheDocument();
  });

  it("lists a lead once it is deleted", async () => {
    signInAs("admin");
    const lead = mockDb.leads[0];
    if (lead === undefined) throw new Error("No seeded lead.");
    await deleteLead({ leadId: lead.id, idempotencyKey: "deleted-list-1" });
    showLeads("deleted=true");

    expect(await screen.findByText(/^1–3 of 3$/)).toBeInTheDocument();
    expect(screen.getByText(lead.inquiry_no)).toBeInTheDocument();
  });

  it("says so when nothing has been deleted", async () => {
    signInAs("admin");
    mockDb.deletedLeads = [];
    showLeads("deleted=true");

    expect(await screen.findByRole("heading", { name: "No deleted leads" })).toBeInTheDocument();
  });

  it("is neither offered nor shown without leads.delete, even by its address", async () => {
    signInAs("district_manager");
    const sent: URL[] = [];
    server.use(
      http.get(buildApiUrl("/leads"), ({ request }) => {
        sent.push(new URL(request.url));
      }),
    );
    showLeads("deleted=true");

    await screen.findByRole("table", { name: "Leads" });
    expect(screen.queryByRole("button", { name: "Deleted leads" })).not.toBeInTheDocument();
    expect(screen.queryByText(/^Deleted leads\./)).not.toBeInTheDocument();
    expect(sent.every((url) => !url.searchParams.has("deleted"))).toBe(true);
  });
});

describe("[LEAD-020] Restoring a deleted lead", () => {
  afterEach(reset);

  it("says when and by whom, and brings the lead back to the leads", async () => {
    signInAs("admin");
    const first = mockDb.deletedLeads[0];
    if (first === undefined) throw new Error("No seeded deleted lead.");
    const sent: string[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST" && new URL(request.url).pathname.endsWith("/restore")) {
        sent.push(request.headers.get("Idempotency-Key") ?? "");
      }
    });
    const user = showLeads("deleted=true");
    await waitFor(() => {
      expect(screen.getByText(/^1–2 of 2$/)).toBeInTheDocument();
    });
    expect(
      screen.getByText(`Deleted 20 Oct by ${first.owner?.full_name ?? ""}`),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: `Restore ${first.farmer_name}` }));

    expect(await screen.findByText("Lead restored")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/^1–1 of 1$/)).toBeInTheDocument();
    });
    expect(mockDb.leads.some((lead) => lead.id === first.id)).toBe(true);
    expect(mockDb.deletedLeads.some((lead) => lead.id === first.id)).toBe(false);
    expect(sent).toHaveLength(1);
    expect(sent[0]).not.toBe("");
    server.events.removeAllListeners();
  });

  it("is open to a state manager, who may delete leads (BE-037)", async () => {
    signInAs("state_manager");
    const user = showLeads();
    await user.click(await screen.findByRole("button", { name: "Deleted leads" }));

    await waitFor(() => {
      expect(screen.getByText(/^1–2 of 2$/)).toBeInTheDocument();
    });
    expect(screen.getAllByRole("button", { name: /^Restore / })).toHaveLength(2);
  });

  it("keeps the lead deleted and says why when the restore is refused", async () => {
    signInAs("admin");
    const first = mockDb.deletedLeads[0];
    if (first === undefined) throw new Error("No seeded deleted lead.");
    server.use(
      http.post(buildApiUrl("/leads/:leadId/restore"), () =>
        HttpResponse.json(
          { error: { code: "forbidden", message: "You may not restore leads." } },
          { status: 403 },
        ),
      ),
    );
    const user = showLeads("deleted=true");
    await user.click(await screen.findByRole("button", { name: `Restore ${first.farmer_name}` }));

    expect(await screen.findByText("Lead not restored")).toBeInTheDocument();
    expect(mockDb.deletedLeads.some((lead) => lead.id === first.id)).toBe(true);
  });
});
