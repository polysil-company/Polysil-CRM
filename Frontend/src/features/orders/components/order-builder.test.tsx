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

  it("[SO-008] keeps a subsidised draft's type when its header changes", async () => {
    signInAs("admin");
    const draft = mockDb.orders.find((order) => order.status === "draft");
    if (draft === undefined) throw new Error("No draft order in the mock database");
    draft.order_type = "subsidised";
    const user = show(<EditOrderDraft orderId={draft.id} />);

    await screen.findByRole("form", { name: /^Edit / });
    expect(screen.getByText(/keeps its type\.$/)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Commercial" })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /^Remarks/ }), "Deliver before sowing");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    }, PRICED);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/sales-orders/${draft.id}`);
    });
    const saved = mockDb.orders.find((order) => order.id === draft.id);
    expect(saved?.order_type).toBe("subsidised");
    expect(saved?.remarks).toBe("Deliver before sowing");
  });

  it("refuses to edit an order that was submitted", async () => {
    signInAs("admin");
    const submitted = mockDb.orders.find((order) => order.status === "submitted");
    if (submitted === undefined) throw new Error("No submitted order in the mock database");
    show(<EditOrderDraft orderId={submitted.id} />);

    expect(await screen.findByText(/was submitted$/)).toBeInTheDocument();
  });
});

describe("[SO-008] A subsidised order typed in", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
    writeMockRole("admin");
  });

  it(
    "names the leads, the first being the order's, and the subsidy, then saves",
    PRICING_TEST,
    async () => {
      signInAs("admin");
      const leadId = leadAt("qualified");
      const other = mockDb.leads.find((lead) => lead.stage === "won" && lead.id !== leadId);
      if (other === undefined) throw new Error("No second orderable lead");
      const user = show(<NewDirectOrder leadId={leadId} />);

      await screen.findByRole("form", { name: "New order" });
      await user.click(screen.getByRole("radio", { name: "Subsidised" }));
      const leads = await screen.findByRole("list", { name: "Leads on this order" });
      expect(within(leads).getByText("(the order's lead)")).toBeInTheDocument();

      await user.type(screen.getByRole("combobox", { name: "Leads" }), other.inquiry_no);
      await user.click(await screen.findByRole("option", { name: new RegExp(other.inquiry_no) }));
      expect(within(leads).getAllByRole("listitem")).toHaveLength(2);

      await addPipe(user, "10");
      await waitFor(() => {
        expect(within(screen.getByLabelText("Totals")).queryByText("—")).not.toBeInTheDocument();
      }, PRICED);
      await user.type(screen.getByRole("textbox", { name: "Subsidy" }), "100");
      await user.click(screen.getByRole("button", { name: "Save draft order" }));

      await waitFor(() => {
        expect(push).toHaveBeenCalledTimes(1);
      });
      const [saved] = mockDb.orders;
      expect(saved).toMatchObject({
        order_type: "subsidised",
        lead: { id: leadId },
        subsidy: {
          subsidy_amount: "100.00",
          material_is_total: true,
          farmer_payable_is_derived: true,
          leads: [{ id: leadId }, { id: other.id }],
        },
      });
    },
  );

  it("asks for the subsidy before saving", PRICING_TEST, async () => {
    signInAs("admin");
    const user = show(<NewDirectOrder leadId={leadAt("qualified")} />);

    await screen.findByRole("form", { name: "New order" });
    await user.click(screen.getByRole("radio", { name: "Subsidised" }));
    await addPipe(user, "10");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save draft order" })).toBeEnabled();
    }, PRICED);
    await user.click(screen.getByRole("button", { name: "Save draft order" }));

    expect(await screen.findByText("Enter the subsidy.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("isn't offered to a dealer", async () => {
    signInAs("dealer");
    show(<NewDirectOrder leadId={null} />);

    await screen.findByRole("form", { name: "New order" });
    expect(screen.getByRole("radio", { name: "Commercial" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Subsidised" })).not.toBeInTheDocument();
  });
});

describe("[QUOT-015] An order's GST slab per item, and freight", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
    writeMockRole("admin");
  });

  it("saves a picked slab and the freight on a direct order", PRICING_TEST, async () => {
    signInAs("admin");
    const user = show(<NewDirectOrder leadId={leadAt("qualified")} />);
    await screen.findByRole("form", { name: "New order" });
    await addPipe(user, "10");
    const item = screen.getByRole("listitem", { name: "Item 1" });
    await within(item).findByText("Rate", {}, PRICED);

    await user.click(within(item).getByRole("combobox", { name: "GST for item 1" }));
    await user.click(await screen.findByRole("option", { name: "40%" }));
    await user.type(screen.getByLabelText("Freight before tax (optional)"), "800");
    await user.click(screen.getByRole("combobox", { name: "GST on freight" }));
    await user.click(await screen.findByRole("option", { name: "5%" }));
    expect(await screen.findByText(/^GST 5%:/, {}, PRICED)).toBeInTheDocument();

    const save = screen.getByRole("button", { name: "Save draft order" });
    await waitFor(() => {
      expect(save).toBeEnabled();
    }, PRICED);
    await user.click(save);
    await waitFor(() => {
      expect(push).toHaveBeenCalledTimes(1);
    });
    const [saved] = mockDb.orders;
    expect(saved?.lines[0]).toMatchObject({ gst_slab: "40.000", gst_slab_chosen: true });
    expect(saved?.freight).toMatchObject({
      amount: "800.00",
      gst_slab: "5.000",
      gst_slab_chosen: true,
      total: "840.00",
    });
    expect(saved?.gst_changed_lines).toBe(1);
  });

  it("puts a refused freight on the freight field", PRICING_TEST, async () => {
    signInAs("admin");
    server.use(
      http.post(buildApiUrl("/orders"), () =>
        HttpResponse.json(
          {
            error: {
              code: "freight_not_allowed",
              message: "Freight is for commercial and industrial documents only.",
              fields: { freight: "Not allowed." },
            },
          },
          { status: 422 },
        ),
      ),
    );
    const user = show(<NewDirectOrder leadId={leadAt("qualified")} />);
    await screen.findByRole("form", { name: "New order" });
    await addPipe(user, "10");
    await within(screen.getByRole("listitem", { name: "Item 1" })).findByText("Rate", {}, PRICED);
    await user.type(screen.getByLabelText("Freight before tax (optional)"), "800");
    const save = screen.getByRole("button", { name: "Save draft order" });
    await waitFor(() => {
      expect(save).toBeEnabled();
    }, PRICED);
    await user.click(save);

    expect(await screen.findByText("Not allowed.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
