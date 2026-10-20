import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  actOnMarketingOrder,
  createMarketingOrder,
  createMaterial,
  dispatchMarketingOrder,
  getMarketingOrder,
  listMarketingOrders,
} from "@/features/marketing/api/marketing.api";
import { previewShares } from "@/features/marketing/lib/marketing-labels";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockMarketingId } from "@/mocks/data/marketing";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { MarketingPage } from "./marketing-page";

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
  return `marketing-test-${String(keys)}`;
}

/** The seeded orders: the dealer's waiting, an officer's approved, and the rest. */
const WAITING = mockMarketingId(2, 4);
const APPROVED = mockMarketingId(2, 3);

function materialCode(code: string): string {
  const material = mockDb.materials.find((item) => item.code === code);
  if (material === undefined) throw new Error(`No material ${code}`);
  return material.id;
}

function reset(role: Role = "district_manager"): void {
  resetMockDb();
  signInAs(role);
}

describe("[MKT-003] Marketing orders (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("splits a dealer's order by the item's share, and an office's own use to the company", async () => {
    reset("dealer");
    const order = await createMarketingOrder({
      body: {
        partner_id: null,
        lines: [{ material_id: materialCode("MM-CAP"), qty: 10 }],
        remark: null,
      },
      idempotencyKey: key(),
    });
    expect(order.status).toBe("submitted");
    expect(order.partner?.name).toBe("Shah Agro Traders");
    expect(order.totals).toEqual({
      value: "1200.00",
      companyShare: "600.00",
      dealerShare: "600.00",
    });

    reset("employee");
    const office = await createMarketingOrder({
      body: {
        partner_id: null,
        lines: [{ material_id: materialCode("MM-PEN"), qty: 100 }],
        remark: null,
      },
      idempotencyKey: key(),
    });
    expect(office.partner).toBeNull();
    expect(office.totals.dealerShare).toBe("0.00");
  });

  it("refuses an item that is switched off", async () => {
    reset("dealer");
    const code = await codeOf(
      createMarketingOrder({
        body: {
          partner_id: null,
          lines: [{ material_id: materialCode("MM-CALENDAR"), qty: 1 }],
          remark: null,
        },
        idempotencyKey: key(),
      }),
    );
    expect(code).toBe("material_inactive");
  });

  it("matches the preview to the backend's figures", () => {
    reset();
    const cap = mockDb.materials.find((item) => item.code === "MM-CAP");
    if (cap === undefined) throw new Error("No cap");
    const material = {
      id: cap.id,
      code: cap.code,
      name: cap.name,
      description: null,
      unit: cap.unit,
      price: cap.price,
      companySharePct: cap.company_share_pct,
      active: true,
      provisional: true,
    };
    expect(previewShares({ [cap.id]: 3 }, [material], false)).toEqual({
      value: "360.00",
      companyShare: "180.00",
      dealerShare: "180.00",
    });
    expect(previewShares({ [cap.id]: 3 }, [material], true).dealerShare).toBe("0.00");
  });
});

describe("[MKT-004] Deciding and sending (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("lets the District Manager decide once, and needs a reason to refuse", async () => {
    reset("district_manager");
    expect((await getMarketingOrder(WAITING)).can).toMatchObject({ approve: true, reject: true });
    expect(
      await codeOf(
        actOnMarketingOrder(WAITING, "reject", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("remark_required");
    const approved = await actOnMarketingOrder(WAITING, "approve", {
      body: { remark: null },
      idempotencyKey: key(),
    });
    expect(approved.status).toBe("approved");
    expect(
      await codeOf(
        actOnMarketingOrder(WAITING, "approve", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("status_changed");
  });

  it("never lets anyone approve their own order", async () => {
    reset("district_manager");
    const mine = await createMarketingOrder({
      body: {
        partner_id: null,
        lines: [{ material_id: materialCode("MM-PEN"), qty: 10 }],
        remark: null,
      },
      idempotencyKey: key(),
    });
    expect(mine.can.approve).toBe(false);
    expect(
      await codeOf(
        actOnMarketingOrder(mine.id, "approve", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("own_order");
  });

  it("records a dispatch, never dated ahead", async () => {
    reset("admin");
    const future = await dispatchMarketingOrder(APPROVED, {
      body: { dispatched_on: shiftCalendarDay(todayInIndia(), 1), reference: "DTDC 1" },
      idempotencyKey: key(),
    }).then(
      () => null,
      (caught: unknown) => caught,
    );
    expect(isApiError(future) && future.status).toBe(422);
    const sent = await dispatchMarketingOrder(APPROVED, {
      body: { dispatched_on: todayInIndia(), reference: "DTDC 1" },
      idempotencyKey: key(),
    });
    expect(sent.status).toBe("dispatched");
    expect(sent.dispatch?.reference).toBe("DTDC 1");
  });

  it("hides who decided from a dealer, and lists only its own orders", async () => {
    reset("dealer");
    const page = await listMarketingOrders({ view: "all", cursor: null });
    expect(page.items.every((order) => order.partner?.id === "prt-201")).toBe(true);
    const refused = await getMarketingOrder(mockMarketingId(2, 1));
    expect(refused.decision?.status).toBe("rejected");
    expect(refused.decision?.by).toBeNull();
  });
});

describe("[MKT-002] The catalogue (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("refuses a taken code and partners", async () => {
    reset("admin");
    const body = {
      code: "MM-CAP",
      name: "Another cap",
      description: null,
      unit: "Nos",
      price: "100",
      company_share_pct: "50",
    };
    expect(await codeOf(createMaterial({ body, idempotencyKey: key() }))).toBe("code_taken");
    reset("dealer");
    const refused = await createMaterial({
      body: { ...body, code: "MM-NEW" },
      idempotencyKey: key(),
    }).then(
      () => null,
      (caught: unknown) => caught,
    );
    expect(isApiError(refused) && refused.status).toBe(403);
  });
});

describe("[MKT-003] MarketingPage", () => {
  afterEach(() => {
    reset();
  });

  function show(searchParams = ""): ReturnType<typeof userEvent.setup> {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <MarketingPage />
        <Toaster />
      </>,
      { searchParams },
    );
    return user;
  }

  it("lets a dealer fill a basket, see both shares and place the order", async () => {
    reset("dealer");
    const user = show();
    const catalogue = await screen.findByRole("list", { name: "Catalogue" });
    expect(screen.queryByRole("tab", { name: "Catalogue" })).toBeNull();
    await user.click(within(catalogue).getByRole("button", { name: "Add POLYSIL CAP" }));
    await user.click(within(catalogue).getByRole("button", { name: "One more POLYSIL CAP" }));
    const costs = screen.getByLabelText("What it costs");
    expect(costs).toHaveTextContent("₹240.00");
    expect(costs).toHaveTextContent("Company pays₹120.00");
    await user.click(screen.getByRole("button", { name: "Place order" }));
    expect(await screen.findByText(/Order MM\/GJ\/2026-27\/\d+ placed/)).toBeInTheDocument();
    expect(await screen.findByRole("dialog")).toHaveTextContent("Waiting for approval");
  });

  it("shows the District Manager the orders to approve, and approves one", async () => {
    reset("district_manager");
    const user = show("?tab=orders");
    const list = await screen.findByRole("list", { name: "Marketing orders" });
    await user.click(within(list).getByRole("button", { name: /^Open MM\/GJ\/2026-27\/00004/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("button", { name: "Approve" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Order approved")).toBeInTheDocument();
  });

  it("asks why before refusing", async () => {
    reset("district_manager");
    const user = show(`?tab=orders&order=${WAITING}`);
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("button", { name: "Refuse" }));
    const form = await screen.findByRole("form", { name: "Refuse this order?" });
    await user.click(within(form).getByRole("button", { name: "Refuse" }));
    expect(await within(form).findByText("Say why.")).toBeInTheDocument();
  });

  it("lets the marketing team record a dispatch and keep the catalogue", async () => {
    reset("admin");
    const user = show(`?tab=orders&view=dispatch&order=${APPROVED}`);
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("button", { name: "Record dispatch" }));
    const form = await screen.findByRole("form", { name: "Record the dispatch" });
    await user.type(within(form).getByLabelText("Reference"), "DTDC 9981");
    await user.click(within(form).getByRole("button", { name: "Record dispatch" }));
    expect(await screen.findByText("Dispatch recorded")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("tab", { name: "Catalogue" }));
    const items = await screen.findByRole("list", { name: "Catalogue items" });
    expect(within(items).getByText("Switched off")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add an item" }));
    const add = await screen.findByRole("form", { name: "Add a catalogue item" });
    await user.type(within(add).getByLabelText("Code"), "MM-CAP");
    await user.type(within(add).getByLabelText("Name"), "Cap again");
    await user.type(within(add).getByLabelText("Price"), "99");
    await user.click(within(add).getByRole("button", { name: "Add item" }));
    expect(await within(add).findByText("That code is taken.")).toBeInTheDocument();
  });
});
