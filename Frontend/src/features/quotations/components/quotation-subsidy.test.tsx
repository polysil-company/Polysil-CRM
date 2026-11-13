import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  createQuotation,
  getQuotationSubsidyCalculation,
  sendQuotation,
  setQuotationSubsidy,
} from "@/features/quotations/api/quotations.api";
import type { Quotation } from "@/features/quotations/api/quotations.schemas";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { QuotationDetail } from "./quotation-detail";
import { QuotationSubsidyStep } from "./quotation-subsidy";

const push = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push }),
}));

const SETTLE = { timeout: 4000 };
let keys = 0;

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

/** A subsidised draft on a qualified drip lead in Gujarat (GGRC), with one item. */
async function subsidisedDraft(): Promise<Quotation> {
  const lead = mockDb.leads.find((item) => item.stage === "qualified");
  const product = MOCK_PRODUCTS[0];
  if (lead === undefined || product === undefined) throw new Error("No qualified lead or product");
  lead.inquiry_type = "subsidised";
  lead.mis_system = "drip";
  keys += 1;
  return createQuotation({
    body: {
      lead_id: lead.id,
      sales_type: "subsidised",
      party: { name: "Ramesh Patel", mobile: "+919876543210", address: null, gstin: null },
      terms: null,
      lines: [
        {
          product_id: product.id,
          qty: "10",
          discount_pct: "0",
          discount2_pct: "0",
          discount3_pct: "0",
        },
      ],
    },
    idempotencyKey: `subsidy-test-${String(keys)}`,
  });
}

const CALCULATION = {
  system_type: "drip" as const,
  crops: [
    {
      crop: null,
      inter_crop: null,
      area: "1.02",
      crop_spacing: "",
      lateral_spacing: "1.2",
      lines: [],
    },
  ],
  head_lines: [],
};

describe("[QUOT-014] The subsidy, through the API", () => {
  afterEach(reset);

  it("is needed before a subsidised draft is sent", async () => {
    signInAs("admin");
    const draft = await subsidisedDraft();
    expect(draft.subsidy).toBeNull();
    await expect(
      sendQuotation(draft.id, {
        body: { channel: "none", expected_status: "draft" },
        idempotencyKey: "send-1",
      }),
    ).rejects.toMatchObject({ status: 422, code: "subsidy_missing" });
  });

  it("stores one category's figures, and the full calculation with it", async () => {
    signInAs("admin");
    const draft = await subsidisedDraft();

    const saved = await setQuotationSubsidy(draft.id, {
      body: { category_code: "small_farmer", calculation: CALCULATION },
      idempotencyKey: "sub-1",
    });

    expect(saved.subsidy).toMatchObject({
      scheme: "GGRC",
      systemType: "drip",
      category: { code: "small_farmer" },
    });
    expect(Number(saved.subsidy?.subsidy)).toBeGreaterThan(0);
    const stored = await getQuotationSubsidyCalculation(draft.id);
    expect(stored.crops).toHaveLength(1);
  });

  it("refuses a category that doesn't apply, and a quotation that isn't subsidised", async () => {
    signInAs("admin");
    const draft = await subsidisedDraft();
    await expect(
      setQuotationSubsidy(draft.id, {
        body: { category_code: "nobody", calculation: CALCULATION },
        idempotencyKey: "sub-2",
      }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { category_code: expect.any(String) } },
    });

    const plain = mockDb.quotations.find((item) => item.id === draft.id);
    if (plain === undefined) throw new Error("No draft");
    plain.sales_type = "commercial";
    await expect(
      setQuotationSubsidy(draft.id, {
        body: { category_code: "small_farmer", calculation: CALCULATION },
        idempotencyKey: "sub-3",
      }),
    ).rejects.toMatchObject({ status: 422, code: "not_subsidised" });
  });
});

describe("[QUOT-014] The subsidy on the quotation", () => {
  afterEach(reset);

  it("says a draft has none yet, and links to the calculator", async () => {
    signInAs("admin");
    const draft = await subsidisedDraft();
    renderWithProviders(<QuotationDetail quotationId={draft.id} />);

    expect(
      await screen.findByText(
        "Not calculated yet. A subsidised quotation is sent with its subsidy.",
      ),
    ).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Calculate the subsidy" })).toHaveAttribute(
      "href",
      `/quotations/${draft.id}/subsidy`,
    );
  });

  it("shows what the scheme and the farmer pay, and the full calculation on asking", async () => {
    signInAs("admin");
    const draft = await subsidisedDraft();
    await setQuotationSubsidy(draft.id, {
      body: { category_code: "small_farmer", calculation: CALCULATION },
      idempotencyKey: "sub-4",
    });
    const user = userEvent.setup();
    renderWithProviders(<QuotationDetail quotationId={draft.id} />);

    expect(await screen.findByText("The scheme pays")).toBeInTheDocument();
    expect(screen.getByText("The farmer pays")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Recalculate" })).toBeInTheDocument();
    // the lines and the calculation don't match here, so the card says so in words
    expect(
      screen.getByText(/The calculation's total differs from the quotation's lines/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show the full calculation" }));
    expect(
      await screen.findByRole("region", { name: "Quotation summary table" }),
    ).toBeInTheDocument();
  });
});

describe("[QUOT-014] The subsidy step", () => {
  afterEach(reset);

  it("calculates on the lead's scheme and system, then saves the chosen category", async () => {
    signInAs("admin");
    const draft = await subsidisedDraft();
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <QuotationSubsidyStep quotationId={draft.id} />
        <Toaster />
      </>,
    );

    await user.type(await screen.findByRole("textbox", { name: /^Area/ }, SETTLE), "1.02");
    await user.type(screen.getByRole("textbox", { name: /^Lateral spacing/ }), "1.2");
    const form = await screen.findByRole("form", { name: "Save the subsidy" });
    const option = await within(form).findByRole("radio", { name: /^Small Farmer/ }, SETTLE);
    await user.click(option);
    await user.click(within(form).getByRole("button", { name: "Save the subsidy" }));

    expect(await screen.findByText("Subsidy saved", { selector: "[data-title]" })).toBeVisible();
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(`/quotations/${draft.id}`);
    });
  });

  it("says a sent quotation's subsidy can't change", async () => {
    signInAs("admin");
    const draft = await subsidisedDraft();
    const stored = mockDb.quotations.find((item) => item.id === draft.id);
    if (stored === undefined) throw new Error("No draft");
    stored.status = "sent";
    renderWithProviders(<QuotationSubsidyStep quotationId={draft.id} />);

    expect(
      await screen.findByText("Only a draft's subsidy can be calculated."),
    ).toBeInTheDocument();
  });
});
