import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { OrderDetail } from "@/features/orders/components/order-detail";
import {
  getOrderWarranty,
  listWarrantyTerms,
  setWarrantyTerm,
} from "@/features/warranty/api/warranty.api";
import type { WarrantyTerm } from "@/features/warranty/api/warranty.schemas";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ComplaintWarranty } from "./warranty-chip";
import { termPhase, termProblems, WarrantyTermsPanel } from "./warranty-terms-panel";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

let keys = 0;
function key(): string {
  keys += 1;
  return `warranty-test-${String(keys)}`;
}

/** A seeded order with goods already sent. */
function shippedOrder(): { id: string; draft: boolean } {
  const order = mockDb.orders.find((item) =>
    item.dispatches.some((dispatch) => dispatch.voided_at === null),
  );
  if (order === undefined) throw new Error("No shipped order in the seed");
  return { id: order.id, draft: false };
}

function term(overrides: Partial<WarrantyTerm>): WarrantyTerm {
  return {
    id: "t-1",
    category: null,
    months: 12,
    effectiveFrom: "2026-04-01",
    effectiveTo: null,
    ...overrides,
  };
}

describe("[SO-009] Order warranty (contract)", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("gives each sent line a period from its dispatch", async () => {
    resetMockDb();
    signInAs("admin");
    const warranty = await getOrderWarranty(shippedOrder().id);
    const sent = warranty.lines.filter((line) => line.dispatches.length > 0);
    expect(sent.length).toBeGreaterThan(0);
    for (const line of sent) {
      expect(line.status).not.toBe("not_dispatched");
      expect(line.dispatches[0]?.start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it("refuses those who can't see dispatches", async () => {
    resetMockDb();
    signInAs("account_manager");
    expect(await codeOf(getOrderWarranty(shippedOrder().id))).toBe("forbidden");
  });
});

describe("[SO-009] OrderWarrantyCard", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("shows the warranty on a shipped order", async () => {
    resetMockDb();
    signInAs("admin");
    renderWithProviders(<OrderDetail orderId={shippedOrder().id} />);
    const card = await screen.findByRole("region", { name: "Warranty" });
    const items = await within(card).findByRole("list", { name: "Warranty by item" });
    expect(
      within(items).getAllByText(/In warranty|Expired|No warranty|No period/).length,
    ).toBeGreaterThan(0);
  });

  it("is hidden from those who can't see dispatches", async () => {
    resetMockDb();
    signInAs("account_manager");
    renderWithProviders(<OrderDetail orderId={shippedOrder().id} />);
    await screen.findByRole("region", { name: "Payments" });
    expect(screen.queryByRole("region", { name: "Warranty" })).toBeNull();
  });

  it("hides itself on a 403", async () => {
    resetMockDb();
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/orders/:orderId/warranty"), () =>
        HttpResponse.json({ error: { code: "forbidden", message: "No." } }, { status: 403 }),
      ),
    );
    renderWithProviders(<OrderDetail orderId={shippedOrder().id} />);
    await screen.findByRole("region", { name: "Payments" });
    await vi.waitFor(() => {
      expect(screen.queryByRole("region", { name: "Warranty" })).toBeNull();
    });
  });
});

describe("[CMPL-011] ComplaintWarranty", () => {
  it("says in or out, until when, and from what", () => {
    render(
      <ComplaintWarranty
        warranty={{
          status: "in_warranty",
          start: "2026-05-01",
          end: "2027-04-30",
          months: 12,
          basis: "dispatch",
        }}
      />,
    );
    expect(screen.getByText("In warranty")).toBeInTheDocument();
    expect(screen.getByText(/until .*2027, from the dispatch/)).toBeInTheDocument();
  });

  it("reads the supply date when no dispatch is linked", () => {
    render(
      <ComplaintWarranty
        warranty={{
          status: "expired",
          start: "2024-01-01",
          end: "2024-12-31",
          months: 12,
          basis: "supply_date",
        }}
      />,
    );
    expect(screen.getByText("Out of warranty")).toBeInTheDocument();
    expect(screen.getByText(/ended .*2024, from the supply date/)).toBeInTheDocument();
  });

  it("shows nothing without a warranty answer", () => {
    const { container } = render(<ComplaintWarranty warranty={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("[MSTR-017] Warranty periods (rules)", () => {
  it("places a period in force, upcoming or ended", () => {
    const today = "2026-10-17";
    expect(termPhase(term({}), today)).toBe("in_force");
    expect(termPhase(term({ effectiveFrom: "2026-11-01" }), today)).toBe("upcoming");
    expect(termPhase(term({ effectiveTo: "2026-10-17" }), today)).toBe("ended");
  });

  it("asks for whole months up to 120 and a day after today", () => {
    const today = "2026-10-17";
    expect(termProblems({ category: "default", months: "121", from: "2026-10-18" }, today)).toEqual(
      {
        months: "Whole months, 0 to 120.",
      },
    );
    expect(
      termProblems({ category: "default", months: "1.5", from: "2026-10-18" }, today).months,
    ).toBeDefined();
    expect(
      termProblems({ category: "default", months: "0", from: "2026-10-17" }, today).from,
    ).toMatch(/Tomorrow/);
    expect(termProblems({ category: "default", months: "24", from: "2026-10-18" }, today)).toEqual(
      {},
    );
  });
});

describe("[MSTR-017] Warranty periods (contract)", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("closes the period in force when a new one starts", async () => {
    resetMockDb();
    signInAs("admin");
    const from = shiftCalendarDay(todayInIndia(), 10);
    const terms = await setWarrantyTerm({
      body: { product_category_id: null, months: 18, effective_from: from },
      idempotencyKey: key(),
    });
    const defaults = terms.filter((item) => item.category === null);
    expect(defaults.find((item) => item.effectiveFrom === from)?.months).toBe(18);
    expect(defaults.filter((item) => item.effectiveTo === null)).toHaveLength(1);
    expect(defaults.some((item) => item.effectiveTo === from)).toBe(true);
  });

  it("refuses today, a second period on the same day, and those who can't edit", async () => {
    resetMockDb();
    signInAs("admin");
    const body = { product_category_id: null, months: 6, effective_from: todayInIndia() };
    expect(await codeOf(setWarrantyTerm({ body, idempotencyKey: key() }))).toBe(
      "validation_failed",
    );
    const later = { ...body, effective_from: shiftCalendarDay(todayInIndia(), 5) };
    await setWarrantyTerm({ body: later, idempotencyKey: key() });
    expect(await codeOf(setWarrantyTerm({ body: later, idempotencyKey: key() }))).toBe(
      "term_exists",
    );
    expect((await listWarrantyTerms()).length).toBeGreaterThan(0);
    signInAs("employee");
    expect(await codeOf(setWarrantyTerm({ body: later, idempotencyKey: key() }))).toBe("forbidden");
  });
});

describe("[MSTR-017] WarrantyTermsPanel", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("lists the periods and sets a new one", async () => {
    resetMockDb();
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <WarrantyTermsPanel canEdit />
        <Toaster />
      </>,
    );
    const list = await screen.findByRole("list", { name: "Warranty periods" });
    expect(within(list).getByText("Drip components")).toBeInTheDocument();
    expect(within(list).getAllByText("In force").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Set a period" }));
    const form = await screen.findByRole("form", { name: "Set a warranty period" });
    await user.type(within(form).getByLabelText("Months"), "18");
    await user.click(within(form).getByRole("button", { name: "Set the period" }));
    expect(await screen.findByText("Warranty period set")).toBeInTheDocument();
    expect(await within(list).findByText("Upcoming")).toBeInTheDocument();
  });

  it("puts a clash on the start day", async () => {
    resetMockDb();
    signInAs("admin");
    await setWarrantyTerm({
      body: {
        product_category_id: null,
        months: 6,
        effective_from: shiftCalendarDay(todayInIndia(), 1),
      },
      idempotencyKey: key(),
    });
    const user = userEvent.setup();
    renderWithProviders(<WarrantyTermsPanel canEdit />);
    await screen.findByRole("list", { name: "Warranty periods" });
    await user.click(screen.getByRole("button", { name: "Set a period" }));
    const form = await screen.findByRole("form", { name: "Set a warranty period" });
    await user.type(within(form).getByLabelText("Months"), "9");
    await user.click(within(form).getByRole("button", { name: "Set the period" }));
    expect(await within(form).findByText(/already starts that day/)).toBeInTheDocument();
  });

  it("offers no change to those who only read", async () => {
    resetMockDb();
    signInAs("admin");
    renderWithProviders(<WarrantyTermsPanel canEdit={false} />);
    await screen.findByRole("list", { name: "Warranty periods" });
    expect(screen.queryByRole("button", { name: "Set a period" })).toBeNull();
  });
});
