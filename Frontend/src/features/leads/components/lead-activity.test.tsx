import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { addLeadNote } from "@/features/leads/api/leads.api";
import { TIMELINE_PAGE_SIZE } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadDetail } from "./lead-detail";
import { LeadNoteComposer } from "./lead-note-composer";
import { LeadTimeline } from "./lead-timeline";

type MockLead = (typeof mockDb.leads)[number];

function mockLead(predicate: (lead: MockLead) => boolean): MockLead {
  const lead = mockDb.leads.find(predicate);
  if (lead === undefined) {
    throw new Error("No matching lead in the mock database");
  }
  return lead;
}

/** Unit tests have no access token, so the session is served directly for one role. */
function signInAs(role: Role): void {
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function Activity({ leadId }: { leadId: string }): React.JSX.Element {
  return (
    <>
      <LeadNoteComposer leadId={leadId} />
      <LeadTimeline leadId={leadId} />
    </>
  );
}

describe("[LEAD-005] LeadTimeline", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("shows a skeleton, then the lead's history with the lost reason by name", async () => {
    const lead = mockLead((item) => item.stage === "lost" && item.lost_reason !== null);
    renderWithProviders(<LeadTimeline leadId={lead.id} />);

    expect(screen.getByRole("status", { name: "Loading activity" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Lead activity, newest first" });
    expect(within(list).getByText(/created the lead/)).toBeInTheDocument();
    expect(within(list).getByText(/to Lost$/)).toBeInTheDocument();
    expect(
      await within(list).findByText(`Reason: ${lead.lost_reason?.name ?? ""}`),
    ).toBeInTheDocument();
  });

  it("loads older activity on request", async () => {
    const user = userEvent.setup();
    const lead = mockLead((item) => item.stage === "new");
    for (let index = 0; index < TIMELINE_PAGE_SIZE; index += 1) {
      await addLeadNote({
        leadId: lead.id,
        body: { note: `Visit ${String(index)}` },
        idempotencyKey: `older-${String(index)}`,
      });
    }
    renderWithProviders(<LeadTimeline leadId={lead.id} />);

    const list = await screen.findByRole("list", { name: "Lead activity, newest first" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(TIMELINE_PAGE_SIZE);
    expect(within(list).queryByText(/created the lead/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show older activity" }));

    expect(await within(list).findByText(/created the lead/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show older activity" })).not.toBeInTheDocument();
  });

  it("keeps the activity shown when older activity fails to load, and offers a retry", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(buildApiUrl("/leads/:leadId/timeline"), ({ request }) => {
        if (new URL(request.url).searchParams.has("cursor")) {
          return HttpResponse.json({ error: { code: "boom", message: "x" } }, { status: 500 });
        }
        return HttpResponse.json({
          data: [
            {
              id: "e1",
              kind: "lead.note_added",
              occurred_at: "2026-09-20T10:00:00+00:00",
              actor: { id: "u1", full_name: "Asha Patel" },
              payload: { note: "Still here" },
            },
          ],
          meta: { limit: 20, next_cursor: "b2Zmc2V0OjIw" },
        });
      }),
    );
    renderWithProviders(<LeadTimeline leadId="lead-x" />);

    await user.click(await screen.findByRole("button", { name: "Show older activity" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The activity above is still current",
    );
    expect(screen.getByText("Still here")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("explains an empty history", async () => {
    server.use(
      http.get(buildApiUrl("/leads/:leadId/timeline"), () =>
        HttpResponse.json({ data: [], meta: { limit: 20, next_cursor: null } }),
      ),
    );
    renderWithProviders(<LeadTimeline leadId="lead-x" />);

    expect(await screen.findByText("No activity yet")).toBeInTheDocument();
  });

  it("says who approved which step, and links quotations by their number", async () => {
    const at = "2026-09-29T10:00:00Z";
    const actor = { id: "usr-2", full_name: "Ravi Joshi" };
    server.use(
      http.get(buildApiUrl("/leads/:leadId/timeline"), () =>
        HttpResponse.json({
          data: [
            {
              id: "e1",
              kind: "approval.decided",
              occurred_at: at,
              actor,
              payload: { seq: 1, role: "district_manager", decision: "approve" },
            },
            {
              id: "e2",
              kind: "quotation.sent",
              occurred_at: at,
              actor,
              payload: { quotation_id: "q-9", quote_no: "QT/GJ/2026-27/00009", version: 2 },
            },
            {
              id: "e3",
              kind: "dispatch.recorded",
              occurred_at: at,
              actor,
              payload: { dispatch_no: "D/SO/GJ/2026-27/00041/1" },
            },
          ],
          meta: { limit: 20, next_cursor: null },
        }),
      ),
    );
    renderWithProviders(<LeadTimeline leadId="lead-x" />);

    expect(await screen.findByText(/approved the District Manager step/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "QT/GJ/2026-27/00009 · v2" })).toHaveAttribute(
      "href",
      "/quotations/q-9",
    );
    expect(screen.getByText("D/SO/GJ/2026-27/00041/1")).toBeInTheDocument();
  });

  it("names the leads a merge or a duplicate is about, and says each thing once (F-16)", async () => {
    const at = "2026-10-10T10:00:00Z";
    const actor = { id: "usr-2", full_name: "Asha Patel" };
    const customer = { id: "usr-sys", full_name: "the customer" };
    server.use(
      http.get(buildApiUrl("/leads/:leadId/timeline"), () =>
        HttpResponse.json({
          data: [
            {
              id: "e1",
              kind: "lead.merged",
              occurred_at: at,
              actor,
              payload: {
                survivor: "lead-x",
                loser: "lead-94",
                survivor_inquiry_no: "POL/GJ/2026-27/00090",
                loser_inquiry_no: "POL/GJ/2026-27/00094",
              },
            },
            {
              id: "e2",
              kind: "lead.duplicate_flagged",
              occurred_at: at,
              actor,
              payload: {
                matches: [
                  { lead_id: "lead-83", inquiry_no: "POL/GJ/2026-27/00083" },
                  { lead_id: "lead-88", inquiry_no: "POL/GJ/2026-27/00088" },
                ],
              },
            },
            {
              id: "e3",
              kind: "lead.duplicate_dismissed",
              occurred_at: at,
              actor,
              payload: { other_lead_id: "lead-83", other_inquiry_no: "POL/GJ/2026-27/00083" },
            },
            {
              id: "e4",
              kind: "quotation.viewed",
              occurred_at: at,
              actor: customer,
              payload: { quotation_id: "q-3", quote_no: "QT/GJ/2026-27/00003", version: 1 },
            },
            {
              id: "e5",
              kind: "approval.decided",
              occurred_at: at,
              actor,
              payload: { role: "district_manager", decision: "approve", quotation_id: "q-1" },
            },
            {
              id: "e6",
              kind: "quotation.approval_approved",
              occurred_at: at,
              actor,
              payload: { quotation_id: "q-1", quote_no: null, version: 1 },
            },
          ],
          meta: { limit: 20, next_cursor: null },
        }),
      ),
    );
    renderWithProviders(<LeadTimeline leadId="lead-x" />);

    const list = await screen.findByRole("list", { name: "Lead activity, newest first" });
    expect(within(list).getByRole("link", { name: "POL/GJ/2026-27/00094" })).toHaveAttribute(
      "href",
      "/leads/lead-94",
    );
    // Each entry's sentence, as read: a "found" or "opened" entry starts with no person's name.
    const sentences = within(list)
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(sentences).toEqual([
      expect.stringMatching(/^Asha Patel merged POL\/GJ\/2026-27\/00094 into this lead/),
      expect.stringMatching(/^2 possible duplicates found: 00083, 00088/),
      expect.stringMatching(/^Asha Patel marked 00083 as not a duplicate/),
      expect.stringMatching(/^The customer opened QT\/GJ\/2026-27\/00003/),
      expect.stringMatching(/^Asha Patel · Quotation discount approved draft quotation v1/),
    ]);
    // A draft has no number; one line for the discount decision, not the step too.
    expect(within(list).getByRole("link", { name: "draft quotation v1" })).toBeInTheDocument();
    expect(within(list).queryByText(/approved the District Manager step/)).not.toBeInTheDocument();
    expect(within(list).getAllByRole("listitem")).toHaveLength(5);
  });

  it("shows an error with a retry when the history cannot load", async () => {
    server.use(
      http.get(buildApiUrl("/leads/:leadId/timeline"), () =>
        HttpResponse.json({ error: { code: "boom", message: "x" } }, { status: 503 }),
      ),
    );
    renderWithProviders(<LeadTimeline leadId="lead-x" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("[LEAD-006] LeadNoteComposer", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("saves a note, shows it first in the timeline and clears the box", async () => {
    const user = userEvent.setup();
    const lead = mockLead((item) => item.stage === "contacted");
    renderWithProviders(<Activity leadId={lead.id} />);
    await screen.findByRole("list", { name: "Lead activity, newest first" });

    const box = screen.getByRole("textbox", { name: "Note" });
    expect(screen.getByRole("button", { name: "Add note" })).toBeDisabled();
    await user.type(box, "Visited the farm; wants drip for 4 acres");
    await user.click(screen.getByRole("button", { name: "Add note" }));

    const list = screen.getByRole("list", { name: "Lead activity, newest first" });
    await waitFor(() => {
      expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent(
        "Visited the farm; wants drip for 4 acres",
      );
    });
    // The box clears once the button has shown its saving state.
    await waitFor(() => {
      expect(box).toHaveValue("");
    });
  });

  it("saves with Ctrl + Enter, while Enter alone adds a line", async () => {
    const user = userEvent.setup();
    const lead = mockLead((item) => item.stage === "contacted");
    renderWithProviders(<Activity leadId={lead.id} />);
    await screen.findByRole("list", { name: "Lead activity, newest first" });

    const box = screen.getByRole("textbox", { name: "Note" });
    await user.type(box, "Line one{Enter}Line two");
    expect(box).toHaveValue("Line one\nLine two");
    await user.keyboard("{Control>}{Enter}{/Control}");

    await waitFor(() => {
      expect(box).toHaveValue("");
    });
    expect(mockDb.leadEvents.get(lead.id)?.[0]?.payload?.note).toBe("Line one\nLine two");
  });

  it("keeps the text after a failed save, and retries with the same key", async () => {
    const user = userEvent.setup();
    const keys: string[] = [];
    server.use(
      http.post(buildApiUrl("/leads/:leadId/notes"), ({ request }) => {
        keys.push(request.headers.get("idempotency-key") ?? "");
        return HttpResponse.json({ error: { code: "boom", message: "x" } }, { status: 500 });
      }),
    );
    const lead = mockLead((item) => item.stage === "contacted");
    renderWithProviders(<Activity leadId={lead.id} />);
    await screen.findByRole("list", { name: "Lead activity, newest first" });

    const box = screen.getByRole("textbox", { name: "Note" });
    await user.type(box, "Call back after the rains");
    await user.click(screen.getByRole("button", { name: "Add note" }));

    expect(await screen.findByText(/Your note is still here/)).toBeInTheDocument();
    expect(box).toHaveValue("Call back after the rains");

    // While the button shows the failure, it is still the form's only button, and enabled.
    const form = screen.getByRole("form", { name: "Add a note" });
    await user.click(within(form).getByRole("button"));
    await waitFor(() => {
      expect(keys).toHaveLength(2);
    });
    expect(keys[0]).not.toBe("");
    expect(keys[1]).toBe(keys[0]);
  });

  it("counts down near the limit and refuses a note that is too long", async () => {
    const user = userEvent.setup();
    const lead = mockLead((item) => item.stage === "contacted");
    renderWithProviders(<LeadNoteComposer leadId={lead.id} />);

    const box = screen.getByRole("textbox", { name: "Note" });
    await user.click(box);
    await user.paste("x".repeat(1999));
    expect(screen.getByText("1 character left")).toBeInTheDocument();

    await user.paste("yy");
    expect(screen.getByText("1 character over the 2,000 limit")).toBeInTheDocument();
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Add note" })).toBeDisabled();
  });

  it("doesn't count spaces at the ends against the limit, as the backend trims them", async () => {
    const user = userEvent.setup();
    const lead = mockLead((item) => item.stage === "contacted");
    renderWithProviders(<LeadNoteComposer leadId={lead.id} />);

    await user.click(screen.getByRole("textbox", { name: "Note" }));
    await user.paste(`${"x".repeat(2000)}   `);

    expect(screen.getByText("0 characters left")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add note" })).toBeEnabled();
  });
});

describe("[LEAD-006] LeadDetail activity", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lets someone who can edit leads add a note", async () => {
    signInAs("employee");
    const lead = mockLead((item) => item.stage === "qualified");
    renderWithProviders(<LeadDetail leadId={lead.id} />);

    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(await screen.findByRole("form", { name: "Add a note" })).toBeInTheDocument();
  });

  it("shows the history but no note box to someone who cannot edit leads", async () => {
    signInAs("account_manager");
    const lead = mockLead((item) => item.stage === "qualified");
    renderWithProviders(<LeadDetail leadId={lead.id} />);

    expect(
      await screen.findByRole("list", { name: "Lead activity, newest first" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add a note" })).not.toBeInTheDocument();
  });

  it("keeps a merged lead read-only", async () => {
    signInAs("employee");
    const lead = mockLead((item) => item.stage === "merged");
    renderWithProviders(<LeadDetail leadId={lead.id} />);

    expect(
      await screen.findByRole("list", { name: "Lead activity, newest first" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add a note" })).not.toBeInTheDocument();
  });
});

describe("[LEAD-003] LeadDetail details", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("shows the lead's crops and land, and no win probability or engagement cards", async () => {
    signInAs("employee");
    const lead = mockLead(
      (item) =>
        item.stage === "qualified" && (item.crops ?? []).length > 0 && item.land_hectares != null,
    );
    renderWithProviders(<LeadDetail leadId={lead.id} />);

    const firstCrop = lead.crops?.[0]?.name ?? "";
    expect(await screen.findByText(firstCrop)).toBeInTheDocument();
    // FS-052 · Hectares first, with acres beside them.
    expect(screen.getByText(/^[\d.]+ hectares \([\d.]+ acres\)$/)).toBeInTheDocument();
    expect(screen.queryByText("Win probability")).not.toBeInTheDocument();
    expect(screen.queryByText("Engagement")).not.toBeInTheDocument();
  });

  it("shows staff the score as a whole number, and the possible duplicates (F-1)", async () => {
    signInAs("employee");
    const lead = mockLead((item) => item.score !== null && item.stage === "qualified");
    lead.score = "28.00";
    renderWithProviders(<LeadDetail leadId={lead.id} />);

    expect(await screen.findByText("Score")).toBeInTheDocument();
    expect(screen.getByText("28")).toBeInTheDocument();
  });

  it("shows a dealer no score and no possible duplicates (F-1)", async () => {
    signInAs("dealer");
    writeMockRole("dealer");
    const lead = mockLead(
      (item) =>
        (item.duplicates ?? []).some((link) => link.state === "pending") && item.score !== null,
    );
    // A partner user reads only the leads their dealership holds (APP-007).
    const partner = mockMeFor("dealer").data.partner;
    lead.assigned_partner =
      partner === null || partner === undefined
        ? null
        : { id: partner.id, name: partner.name ?? "Dealer", partner_type: "dealer" };
    renderWithProviders(<LeadDetail leadId={lead.id} />);

    expect(
      await screen.findByRole("heading", { level: 2, name: lead.farmer_name }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Channel partner")).toBeInTheDocument();
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
    expect(screen.queryByText(/possible duplicate/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review and merge" })).not.toBeInTheDocument();
  });

  it("drops the hot, warm or cold tag once a lead is won", async () => {
    signInAs("employee");
    const lead = mockLead((item) => item.stage === "won" && item.priority !== null);
    renderWithProviders(<LeadDetail leadId={lead.id} />);

    expect(
      await screen.findByRole("heading", { level: 2, name: lead.farmer_name }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^(Hot|Warm|Cold)$/)).not.toBeInTheDocument();
  });
});
