import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DuplicateReview } from "./duplicate-review";
import { LeadDetail } from "./lead-detail";

const push = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push, back: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

function leadAt(stage: string): (typeof mockDb.leads)[number] {
  const lead = mockDb.leads.find((item) => item.stage === stage && item.merged_into === null);
  if (lead === undefined) throw new Error(`No ${stage} lead`);
  return lead;
}

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(ui: React.JSX.Element): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
  );
  return user;
}

function reset(): void {
  push.mockReset();
  resetMockDb();
  writeMockRole("state_manager");
}

describe("[LEAD-010] LeadEditDialog", () => {
  afterEach(reset);

  it("corrects the farmer's name, sending only what changed", async () => {
    signInAs("state_manager");
    const lead = leadAt("contacted");
    const patches: unknown[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "PATCH")
        void request
          .clone()
          .json()
          .then((body) => patches.push(body));
    });
    const user = show(<LeadDetail leadId={lead.id} />);

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    const name = within(dialog).getByLabelText("Farmer name");
    await user.clear(name);
    await user.type(name, "Kiritbhai Shah");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Lead updated")).toBeInTheDocument();
    await waitFor(() => {
      expect(patches).toEqual([{ farmer_name: "Kiritbhai Shah" }]);
    });
    server.events.removeAllListeners();
  });

  it("offers no edit on a closed lead", async () => {
    signInAs("state_manager");
    show(<LeadDetail leadId={leadAt("lost").id} />);

    await screen.findByRole("heading", { name: "Details" });
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });
});

describe("[LEAD-011] LeadDeleteDialog", () => {
  afterEach(reset);

  it("deletes after asking, then goes back to the list", async () => {
    signInAs("admin");
    const lead = leadAt("new");
    const user = show(<LeadDetail leadId={lead.id} />);

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete lead" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/leads");
    });
    expect(mockDb.leads.some((item) => item.id === lead.id)).toBe(false);
  });

  it("is not offered without leads.delete", async () => {
    signInAs("state_manager");
    show(<LeadDetail leadId={leadAt("new").id} />);

    await screen.findByRole("heading", { name: "Details" });
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });
});

describe("[LEAD-012] DuplicateReview", () => {
  afterEach(reset);

  it("shows pairs side by side, and dismisses one", async () => {
    signInAs("state_manager");
    const user = show(<DuplicateReview />);

    const list = await screen.findByRole("list", { name: "Possible duplicates" });
    const [first] = within(list).getAllByRole("listitem");
    if (first === undefined) throw new Error("No pair");
    const before = within(list).getAllByRole("listitem").length;
    await user.click(within(first).getByRole("button", { name: "Not a duplicate" }));

    expect(await screen.findByText("Marked as different people")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(list).queryAllByRole("listitem")).toHaveLength(before - 1);
    });
  });

  it("merges after confirming which lead is kept", async () => {
    signInAs("state_manager");
    const user = show(<DuplicateReview />);

    const list = await screen.findByRole("list", { name: "Possible duplicates" });
    const open = within(list)
      .getAllByRole("listitem")
      .find((item) => within(item).queryAllByRole("button", { name: /^Keep / }).length > 0);
    if (open === undefined) throw new Error("No open pair");
    const [keep] = within(open).getAllByRole("button", { name: /^Keep / });
    if (keep === undefined) throw new Error("No keep button");
    await user.click(keep);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/can't be undone/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /^Merge into / }));

    expect(await screen.findByText("Leads merged")).toBeInTheDocument();
  });

  it("offers no merge when one of the pair is closed", async () => {
    signInAs("state_manager");
    show(<DuplicateReview />);

    const list = await screen.findByRole("list", { name: "Possible duplicates" });
    const closed = within(list)
      .getAllByRole("listitem")
      .find((item) => within(item).queryByRole("note") !== null);
    if (closed === undefined) throw new Error("No closed pair seeded");
    expect(within(closed).queryByRole("button", { name: /^Keep / })).not.toBeInTheDocument();
    expect(within(closed).getByRole("button", { name: "Not a duplicate" })).toBeInTheDocument();
  });

  it("says when nothing waits", async () => {
    signInAs("state_manager");
    for (const lead of mockDb.leads) lead.duplicates = [];
    show(<DuplicateReview />);

    expect(await screen.findByText("No possible duplicates")).toBeInTheDocument();
  });
});
