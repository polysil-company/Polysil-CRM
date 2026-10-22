import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { EditQuotation, NewQuotation } from "./quotation-builder-pages";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

/** Two debounces (search, then pricing) sit between typing and the figures. */
const PRICED = { timeout: 4000 };
/** A test that prices items waits on those debounces more than once. */
const PRICING_TEST = { timeout: 15_000 };

function leadAt(stage: LeadStage): string {
  const lead = mockDb.leads.find((item) => item.stage === stage);
  if (lead === undefined) {
    throw new Error(`No ${stage} lead in the mock database`);
  }
  return lead.id;
}

function quotationWith(status: string): string {
  const quotation = mockDb.quotations.find(
    (item) => item.status === status && item.superseded_by === null,
  );
  if (quotation === undefined) {
    throw new Error(`No ${status} quotation in the mock database`);
  }
  return quotation.id;
}

/** Unit tests have no access token, so the session is served directly. */
function signInAsAdmin(): void {
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor("admin"))));
}

function showNew(leadId: string | null): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <NewQuotation leadId={leadId} />
      <Toaster />
    </>,
  );
  return user;
}

/** Picks the first pipe for item 1 and orders `qty` of it. */
async function addPipe(user: ReturnType<typeof userEvent.setup>, qty: string): Promise<void> {
  const item = await screen.findByRole("listitem", { name: "Item 1" });
  await user.type(within(item).getByLabelText("Product"), "pipe");
  const [option] = await screen.findAllByRole("option", {}, PRICED);
  if (option === undefined) {
    throw new Error("The product search showed no options");
  }
  await user.click(option);
  await user.type(within(item).getByLabelText("Quantity"), qty);
}

describe("[QUOT-004] QuotationBuilder", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it(
    "prices an item as it is entered, then saves the draft and opens it",
    PRICING_TEST,
    async () => {
      signInAsAdmin();
      const user = showNew(leadAt("qualified"));

      await screen.findByRole("form", { name: "New quotation" });
      await addPipe(user, "12");

      const item = screen.getByRole("listitem", { name: "Item 1" });
      expect(await within(item).findByText("Rate", {}, PRICED)).toBeInTheDocument();
      await waitFor(() => {
        expect(within(screen.getByLabelText("Totals")).queryByText("—")).not.toBeInTheDocument();
      }, PRICED);

      const before = mockDb.quotations.length;
      await user.click(screen.getByRole("button", { name: "Save draft" }));

      await waitFor(() => {
        expect(push).toHaveBeenCalledTimes(1);
      });
      const [saved] = mockDb.quotations;
      expect(mockDb.quotations).toHaveLength(before + 1);
      expect(saved?.status).toBe("draft");
      expect(saved?.lines).toHaveLength(1);
      expect(push).toHaveBeenCalledWith(`/quotations/${saved?.id ?? ""}`);
      expect(await screen.findByText("Draft saved")).toBeInTheDocument();
    },
  );

  it(
    "says when prices changed since the preview, and saves once re-priced",
    PRICING_TEST,
    async () => {
      signInAsAdmin();
      const user = showNew(leadAt("qualified"));

      await screen.findByRole("form", { name: "New quotation" });
      await addPipe(user, "5");
      const item = screen.getByRole("listitem", { name: "Item 1" });
      await within(item).findByText("Rate", {}, PRICED);

      mockDb.priceVersion += 1;
      const saveButton = screen.getByRole("button", { name: "Save draft" });
      await user.click(saveButton);

      expect(await screen.findByText("Prices changed since you priced this")).toBeInTheDocument();
      expect(await within(item).findByText(/^Rate: now/)).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();

      // The preview is re-read with the new price list; once it is in, the same click saves.
      await waitFor(() => {
        expect(saveButton).toHaveAttribute("data-state", "idle");
      }, PRICED);
      await waitFor(() => {
        expect(saveButton).toBeEnabled();
      }, PRICED);
      await user.click(saveButton);
      await waitFor(() => {
        expect(push).toHaveBeenCalledTimes(1);
      });
    },
  );

  it("keeps Save off until an item is complete", async () => {
    signInAsAdmin();
    const user = showNew(leadAt("qualified"));

    await screen.findByRole("form", { name: "New quotation" });
    const item = screen.getByRole("listitem", { name: "Item 1" });
    await user.type(within(item).getByLabelText("Quantity"), "3");

    expect(within(item).getByText("Choose a product")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
  });
});

describe("[QUOT-004] NewQuotation", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it("asks to start from a lead when none is given", async () => {
    signInAsAdmin();
    showNew(null);

    expect(await screen.findByText("Start from a lead")).toBeInTheDocument();
  });

  it("explains why a lead that is not qualified can't be quoted", async () => {
    signInAsAdmin();
    showNew(leadAt("new"));

    expect(await screen.findByText(/can't be quoted yet$/)).toBeInTheDocument();
    expect(screen.getByText(/Qualify the lead first/)).toBeInTheDocument();
  });
});

describe("[QUOT-004] EditQuotation", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it("loads a draft's items and header for editing", async () => {
    signInAsAdmin();
    renderWithProviders(<EditQuotation quotationId={quotationWith("draft")} />);

    const form = await screen.findByRole("form", { name: /^Edit / });
    expect(within(form).getByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(within(form).getAllByRole("listitem").length).toBeGreaterThan(0);
  });

  it("does not edit a quotation that was sent", async () => {
    signInAsAdmin();
    renderWithProviders(<EditQuotation quotationId={quotationWith("sent")} />);

    expect(await screen.findByText(/ was sent$/)).toBeInTheDocument();
  });
});

describe("[MSTR-007] Items from Excel", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it("adds a sheet's good rows as items, then prices them as usual", PRICING_TEST, async () => {
    signInAsAdmin();
    const user = showNew(leadAt("qualified"));
    await screen.findByRole("form", { name: "New quotation" });

    await user.click(screen.getByRole("button", { name: "Import from Excel" }));
    const dialog = await screen.findByRole("dialog", { name: "Import items from Excel" });
    await user.upload(
      within(dialog).getByTestId("import-file-input"),
      new File(
        [["Particulars,Qty,Disc %", "INLINE DRIPPER 4 LPH,120,5", "NOT A PRODUCT,2,"].join("\n")],
        "order.csv",
        { type: "text/csv" },
      ),
    );
    await user.click(within(dialog).getByRole("button", { name: "Upload" }));
    await within(dialog).findByRole("list", { name: "Columns in your file" });
    await user.click(within(dialog).getByRole("button", { name: "Check the rows" }));

    expect(await within(dialog).findByText("1 ready")).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: "Add to quotation: the 1 good item" }),
    );

    expect(await screen.findByText("1 item added")).toBeInTheDocument();
    // The empty first row gave way to the imported one.
    const items = screen.getByRole("list", { name: "Items" });
    expect(within(items).getAllByRole("listitem")).toHaveLength(1);
    const item = within(items).getByRole("listitem", { name: "Item 1" });
    expect(within(item).getByLabelText("Quantity")).toHaveValue("120");
    expect(await within(item).findByText("Rate", {}, PRICED)).toBeInTheDocument();
  });
});

describe("[QUOT-015] A GST slab per item, and freight", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
    server.events.removeAllListeners();
  });

  /** The bodies of every preview and save, in order. */
  function recordBodies(): { path: string; body: Record<string, unknown> }[] {
    const bodies: { path: string; body: Record<string, unknown> }[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "GET") return;
      const path = new URL(request.url).pathname;
      void request
        .clone()
        .json()
        .then((body: unknown) => {
          if (typeof body === "object" && body !== null && !Array.isArray(body)) {
            bodies.push({ path, body: Object.fromEntries(Object.entries(body)) });
          }
        });
    });
    return bodies;
  }

  function linesOf(body: Record<string, unknown>): Record<string, unknown>[] {
    const lines = body.lines;
    return Array.isArray(lines)
      ? lines.flatMap((line: unknown) =>
          typeof line === "object" && line !== null
            ? [Object.fromEntries(Object.entries(line))]
            : [],
        )
      : [];
  }

  it(
    "presets an item to its HSN slab, sends a slab only once picked, and saves the freight",
    PRICING_TEST,
    async () => {
      signInAsAdmin();
      const bodies = recordBodies();
      const user = showNew(leadAt("qualified"));
      await screen.findByRole("form", { name: "New quotation" });
      await addPipe(user, "10");
      const item = screen.getByRole("listitem", { name: "Item 1" });
      await within(item).findByText("Rate", {}, PRICED);

      // The pipe's HSN slab is 18 %: shown, and no slab sent for it.
      const gst = within(item).getByRole("combobox", { name: "GST for item 1" });
      expect(gst).toHaveTextContent("18% (HSN)");
      const previews = bodies.filter((entry) => entry.path.endsWith("/pricing/quote-lines"));
      expect(previews.length).toBeGreaterThan(0);
      expect(linesOf(previews.at(-1)?.body ?? {})[0]).not.toHaveProperty("gst_slab");

      await user.click(gst);
      // 0, 5, 18 and 40 from the setting; 18 is the HSN's own.
      expect(await screen.findByRole("option", { name: "40%" })).toBeInTheDocument();
      await user.click(screen.getByRole("option", { name: "5%" }));
      expect(await within(item).findByText("Changed from 18%")).toBeInTheDocument();

      await user.type(screen.getByLabelText("Freight before tax (optional)"), "1500");
      const totals = screen.getByLabelText("Totals");
      expect(await within(totals).findByText("Freight", {}, PRICED)).toBeInTheDocument();
      expect(
        await screen.findByText(/GST 5% \(highest of the items\)/, {}, PRICED),
      ).toBeInTheDocument();

      const save = screen.getByRole("button", { name: "Save draft" });
      await waitFor(() => {
        expect(save).toBeEnabled();
      }, PRICED);
      await user.click(save);
      await waitFor(() => {
        expect(push).toHaveBeenCalledTimes(1);
      });

      const created = bodies.find((entry) => entry.path.endsWith("/quotations"));
      expect(linesOf(created?.body ?? {})[0]).toMatchObject({ gst_slab: "5" });
      expect(created?.body.freight).toEqual({ amount: "1500" });
      const [saved] = mockDb.quotations;
      expect(saved?.lines[0]).toMatchObject({
        gst_slab: "5.000",
        hsn_slab: "18.000",
        gst_slab_chosen: true,
      });
      expect(saved?.gst_changed_lines).toBe(1);
      expect(saved?.freight).toMatchObject({ amount: "1500.00", gst_slab: "5.000" });
      expect(saved?.totals.freight).toBe("1500.00");
    },
  );

  it("says what's wrong with a freight amount on the field, and holds the save", async () => {
    signInAsAdmin();
    const user = showNew(leadAt("qualified"));
    await screen.findByRole("form", { name: "New quotation" });

    await user.type(screen.getByLabelText("Freight before tax (optional)"), "12.345");
    expect(
      await screen.findByText("Rupees above 0, with at most two decimals"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Freight before tax (optional)")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("puts the backend's refusal of a picked slab on its item", PRICING_TEST, async () => {
    signInAsAdmin();
    const user = showNew(leadAt("qualified"));
    await screen.findByRole("form", { name: "New quotation" });
    await addPipe(user, "4");
    const item = screen.getByRole("listitem", { name: "Item 1" });
    await within(item).findByText("Rate", {}, PRICED);

    // The admin takes 5 % off the list after the screen read it.
    server.use(
      http.post(buildApiUrl("/pricing/quote-lines"), () =>
        HttpResponse.json(
          {
            error: {
              code: "gst_slab_not_offered",
              message: "A GST slab may be chosen from the slabs in force.",
              fields: { "lines[0].gst_slab": "5 % is not one of the GST slabs offered." },
            },
          },
          { status: 422 },
        ),
      ),
    );
    await user.click(within(item).getByRole("combobox", { name: "GST for item 1" }));
    await user.click(await screen.findByRole("option", { name: "5%" }));

    expect(
      await within(item).findByText("GST: 5 % is not one of the GST slabs offered.", {}, PRICED),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
  });

  it("offers neither a slab nor freight on a subsidised quotation", async () => {
    signInAsAdmin();
    const lead = mockDb.leads.find((item) => item.stage === "qualified");
    if (lead === undefined) throw new Error("No qualified lead");
    lead.inquiry_type = "subsidised";
    showNew(lead.id);
    await screen.findByRole("form", { name: "New quotation" });

    expect(screen.queryByLabelText("Freight before tax (optional)")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "GST for item 1" })).not.toBeInTheDocument();
  });

  it("loads a draft's picked slab and freight, and sends them again on save", async () => {
    signInAsAdmin();
    const draft = mockDb.quotations.find(
      (item) =>
        item.status === "draft" &&
        item.sales_type === "commercial" &&
        item.superseded_by === null &&
        item.lines.length > 0,
    );
    if (draft === undefined) throw new Error("No commercial draft");
    const [first] = draft.lines;
    if (first === undefined) throw new Error("No line");
    const bodies = recordBodies();
    // Chosen at 40 %, with ₹2,000 freight at the default slab.
    draft.lines[0] = { ...first, gst_slab: "40.000", gst_slab_chosen: true };
    draft.freight = {
      amount: "2000.00",
      gst_slab: "40.000",
      gst_slab_chosen: false,
      cgst_rate: "20.000",
      sgst_rate: "20.000",
      igst_rate: "0.000",
      cgst: "400.00",
      sgst: "400.00",
      igst: "0.00",
      total: "2800.00",
    };
    const user = userEvent.setup();
    renderWithProviders(<EditQuotation quotationId={draft.id} />);

    const form = await screen.findByRole("form", { name: /^Edit / });
    const item = within(form).getByRole("listitem", { name: "Item 1" });
    expect(within(item).getByRole("combobox", { name: "GST for item 1" })).toHaveTextContent("40%");
    expect(within(form).getByLabelText("Freight before tax (optional)")).toHaveValue("2000");

    const save = within(form).getByRole("button", { name: "Save changes" });
    await waitFor(() => {
      expect(save).toBeEnabled();
    }, PRICED);
    await user.click(save);
    await waitFor(() => {
      expect(push).toHaveBeenCalledTimes(1);
    });
    const replaced = bodies.find((entry) => entry.path.endsWith("/lines"));
    expect(linesOf(replaced?.body ?? {})[0]).toMatchObject({ gst_slab: "40" });
    expect(replaced?.body.freight).toEqual({ amount: "2000" });
  });
});
