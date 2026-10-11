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
