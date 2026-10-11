import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { createQuotation } from "@/features/quotations/api/quotations.api";
import type { Quotation } from "@/features/quotations/api/quotations.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { QuotationDetail } from "./quotation-detail";

const push = vi.fn();

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push }),
}));

let keys = 0;

/** Unit tests have no access token, so the session is served directly for one role. */
function signInAs(role: Role): void {
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

/** A draft on a qualified lead with one item at `discountPct`; the owner's limit is 5 %. */
async function draftWith(discountPct: string): Promise<Quotation> {
  const lead = mockDb.leads.find((item) => item.stage === "qualified");
  const product = MOCK_PRODUCTS[0];
  if (lead === undefined || product === undefined) {
    throw new Error("The mock database has no qualified lead or no product");
  }
  keys += 1;
  return createQuotation({
    body: {
      lead_id: lead.id,
      sales_type: "commercial",
      party: { name: "Ramesh Patel", mobile: "+919876543210", address: null, gstin: null },
      terms: null,
      lines: [
        {
          product_id: product.id,
          qty: "10",
          discount_pct: discountPct,
          discount2_pct: "0",
          discount3_pct: "0",
        },
      ],
    },
    idempotencyKey: `actions-test-${String(keys)}`,
  });
}

function currentWith(status: string): string {
  const quotation = mockDb.quotations.find(
    (item) =>
      item.status === status &&
      item.superseded_by === null &&
      item.valid_until !== null &&
      item.valid_until >= new Date().toISOString().slice(0, 10),
  );
  if (quotation === undefined) {
    throw new Error(`No current ${status} quotation in the mock database`);
  }
  return quotation.id;
}

function show(quotationId: string): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <QuotationDetail quotationId={quotationId} />
      <Toaster />
    </>,
  );
  return user;
}

describe("[QUOT-006] Send", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it("sends a draft within the limit, without a message when asked, and shows its number", async () => {
    signInAs("state_manager");
    const draft = await draftWith("0");
    const user = show(draft.id);

    await user.click(await screen.findByRole("button", { name: "Send" }));
    const dialog = await screen.findByRole("dialog", { name: "Send the quotation" });
    await user.click(within(dialog).getByRole("radio", { name: /Don't send a message/ }));
    await user.click(within(dialog).getByRole("button", { name: "Send quotation" }));

    expect(await screen.findByText("Quotation sent")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { level: 2, name: /^QT\/GJ\/2026-27\// }),
    ).toBeInTheDocument();
    expect(mockDb.leads.find((lead) => lead.id === draft.lead?.id)?.stage).toBe("quoted");
  });

  it("closes and shows the latest when someone else moved the quotation", async () => {
    signInAs("state_manager");
    const draft = await draftWith("0");
    server.use(
      http.post(buildApiUrl("/quotations/:quotationId/send"), () =>
        HttpResponse.json(
          {
            error: {
              code: "status_changed",
              message: "moved",
              fields: { status: "sent" },
            },
          },
          { status: 409 },
        ),
      ),
    );
    const user = show(draft.id);

    await user.click(await screen.findByRole("button", { name: "Send" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Send quotation" }));

    expect(await screen.findByText("The quotation has moved on")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});

describe("[QUOT-007] Ask for approval", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("asks for a discount above the limit, then waits for the approver", async () => {
    signInAs("employee");
    const draft = await draftWith("12");
    const user = show(draft.id);

    expect(await screen.findByText("The discount needs a manager's approval")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Ask for approval" }));
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    const dialog = await screen.findByRole("dialog", { name: "Ask for discount approval" });
    await user.type(within(dialog).getByLabelText(/Why is this discount needed/), "Repeat buyer");
    await user.click(within(dialog).getByRole("button", { name: "Ask for approval" }));

    expect(await screen.findByRole("button", { name: "Waiting for approval" })).toBeDisabled();
    expect(
      screen.getByText("Waiting for a State Manager to approve the 12% discount"),
    ).toBeInTheDocument();
  });
});

describe("[QUOT-008] Record answer", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("marks a sent quotation accepted with the customer's words", async () => {
    signInAs("state_manager");
    const user = show(currentWith("viewed"));

    await user.click(await screen.findByRole("button", { name: "Record answer" }));
    await user.click(await screen.findByRole("menuitem", { name: "Accepted…" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as accepted" });
    await user.type(within(dialog).getByLabelText(/What the customer said/), "Confirmed by phone");
    await user.click(within(dialog).getByRole("button", { name: "Mark accepted" }));

    expect(await screen.findByText("Marked accepted")).toBeInTheDocument();
    expect(await screen.findByText("Accepted by the customer", { exact: false })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Record answer" })).not.toBeInTheDocument();
  });
});

describe("[QUOT-009] Revise", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it("drafts the next version and opens it", async () => {
    signInAs("state_manager");
    const user = show(currentWith("viewed"));

    await user.click(await screen.findByRole("button", { name: "Revise" }));
    const dialog = await screen.findByRole("dialog", { name: "Revise into version 2" });
    await user.click(within(dialog).getByRole("button", { name: "Revise" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledTimes(1);
    });
    const [revision] = mockDb.quotations;
    expect(revision?.version).toBe(2);
    expect(push).toHaveBeenCalledWith(`/quotations/${revision?.id ?? ""}`);
  });
});

describe("[QUOT-011] Delete draft", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it("deletes a draft for a role that may, and goes back to its lead", async () => {
    signInAs("admin");
    const draft = await draftWith("0");
    const user = show(draft.id);

    await user.click(await screen.findByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /Delete draft/ }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this draft?" });
    await user.click(within(dialog).getByRole("button", { name: "Delete draft" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/leads/${draft.lead?.id ?? ""}`);
    });
    expect(mockDb.quotations.some((item) => item.id === draft.id)).toBe(false);
  });

  it("offers no delete to a role without the permission", async () => {
    signInAs("state_manager");
    const draft = await draftWith("0");
    show(draft.id);

    expect(await screen.findByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More actions" })).not.toBeInTheDocument();
  });
});
