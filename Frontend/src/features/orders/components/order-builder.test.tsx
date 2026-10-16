import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { EditOrderDraft, NewDirectOrder } from "./order-builder-pages";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

/** Two debounces (search, then pricing) sit between typing and the figures. */
const PRICED = { timeout: 4000 };
const PRICING_TEST = { timeout: 15_000 };

function leadAt(stage: LeadStage): string {
  const lead = mockDb.leads.find((item) => item.stage === stage);
  if (lead === undefined) throw new Error(`No ${stage} lead in the mock database`);
  return lead.id;
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

/** Picks the first pipe for item `n` and orders `qty` of it. */
async function addPipe(
  user: ReturnType<typeof userEvent.setup>,
  qty: string,
  n = 1,
): Promise<void> {
  const item = await screen.findByRole("listitem", { name: `Item ${String(n)}` });
  await user.type(within(item).getByLabelText("Product"), "pipe");
  const [option] = await screen.findAllByRole("option", {}, PRICED);
  if (option === undefined) throw new Error("The product search showed no options");
  await user.click(option);
  await user.type(within(item).getByLabelText("Quantity"), qty);
}

describe("[SO-005] OrderBuilder", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
    writeMockRole("admin");
  });

  it(
    "places a direct order on a qualified lead: priced as typed, saved as a draft",
    PRICING_TEST,
    async () => {
      signInAs("admin");
      const leadId = leadAt("qualified");
      const user = show(<NewDirectOrder leadId={leadId} />);

      await screen.findByRole("form", { name: "New order" });
      // The lead fixes where the goods go.
      expect(screen.getByLabelText("Where the goods go")).toBeDisabled();
      expect(screen.getByRole("button", { name: "Save draft order" })).toBeDisabled();
      expect(screen.getByText("Add at least one item.")).toBeInTheDocument();

      await addPipe(user, "10");
      await waitFor(() => {
        expect(within(screen.getByLabelText("Totals")).queryByText("—")).not.toBeInTheDocument();
      }, PRICED);

      const before = mockDb.orders.length;
      await user.click(screen.getByRole("button", { name: "Save draft order" }));
      await waitFor(() => {
        expect(push).toHaveBeenCalledTimes(1);
      });
      const [saved] = mockDb.orders;
      expect(mockDb.orders).toHaveLength(before + 1);
      expect(saved).toMatchObject({ status: "draft", quotations: [], lead: { id: leadId } });
      expect(saved?.lines).toHaveLength(1);
      expect(push).toHaveBeenCalledWith(`/sales-orders/${saved?.id ?? ""}`);
      expect(await screen.findByText("Order saved as a draft")).toBeInTheDocument();
    },
  );

  it("needs a place of supply before pricing an order typed in afresh", async () => {
    signInAs("admin");
    const user = show(<NewDirectOrder leadId={null} />);

    await screen.findByRole("form", { name: "New order" });
    expect(screen.getByText("Choose where the goods go to see prices.")).toBeInTheDocument();
    expect(screen.getByText("Choose where the goods go first.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Party"), "Kiritbhai Shah");
    expect(screen.getByLabelText("Where the goods go")).toBeEnabled();
  });

  it("says a new lead can't take an order yet", async () => {
    signInAs("admin");
    show(<NewDirectOrder leadId={leadAt("new")} />);

    expect(await screen.findByText(/can't take an order yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the lead" })).toBeInTheDocument();
  });

  it("is closed to someone who may not place orders", async () => {
    signInAs("qa_manager");
    show(<NewDirectOrder leadId={leadAt("qualified")} />);

    expect(await screen.findByText("You don't have access to this")).toBeInTheDocument();
  });

  it("edits a draft's items, then saves every line", PRICING_TEST, async () => {
    signInAs("admin");
    const draft = mockDb.orders.find((order) => order.status === "draft");
    if (draft === undefined) throw new Error("No draft order in the mock database");
    const before = draft.lines.length;
    const user = show(<EditOrderDraft orderId={draft.id} />);

    await screen.findByRole("form", { name: /^Edit / });
    expect(await screen.findAllByRole("listitem", { name: /^Item \d+$/ })).toHaveLength(before);
    await user.click(screen.getByRole("button", { name: "Add item" }));
    await addPipe(user, "3", before + 1);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    }, PRICED);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/sales-orders/${draft.id}`);
    });
    expect(mockDb.orders.find((order) => order.id === draft.id)?.lines).toHaveLength(before + 1);
  });

  it("refuses to edit an order that was submitted", async () => {
    signInAs("admin");
    const submitted = mockDb.orders.find((order) => order.status === "submitted");
    if (submitted === undefined) throw new Error("No submitted order in the mock database");
    show(<EditOrderDraft orderId={submitted.id} />);

    expect(await screen.findByText(/was submitted$/)).toBeInTheDocument();
  });
});
