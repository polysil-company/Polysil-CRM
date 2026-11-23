import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  addCommissionRate,
  decideCommission,
  getCommissionPreview,
  getLiveCommission,
  listCommissionRates,
  payCommission,
  recordCommission,
} from "@/features/commission/api/commission.api";
import { ApplicationDetail } from "@/features/subsidy/components/application-detail";
import { SubsidyMasters } from "@/features/subsidy/components/subsidy-masters";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { mockApplications } from "@/mocks/handlers/subsidy-applications";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { CommissionsList } from "./commissions-list";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
  notFound: vi.fn(),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(ui: React.JSX.Element, searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

/** The seeded application with every payment in, through a sub-dealer. */
function closedApplication(): string {
  const found = mockApplications().find((item) => item.status === "full_fp_received");
  if (found === undefined) throw new Error("No closed application in the seed");
  return found.id;
}

function openApplication(): string {
  const found = mockApplications().find((item) => item.status === "open");
  if (found === undefined) throw new Error("No open application in the seed");
  return found.id;
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
  return `commission-test-${String(keys)}`;
}

/** Fittings that leave a round base: ₹1,10,570.30 − 3,000 − 1,570.30 − 4,000 = ₹1,02,000. */
const ROUND = {
  gi_fitting: "3000",
  pvc_hdpe_fitting: "1570.30",
  installation: null,
  tod_base: null,
  remark: null,
};

describe("[SUBS-016] Stage 18 — the contract", () => {
  beforeEach(() => {
    writeMockRole("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("previews the cost and the rate in force, and refuses an application still open", async () => {
    const preview = await getCommissionPreview(closedApplication());
    expect(preview).toMatchObject({
      partner: { name: "Babra Farm Supplies" },
      costExclGst: "110570.30",
      installation: "4000.00",
      // A sub-dealer has no rate of its own, so the scheme-wide one applies.
      commissionPct: "5.00",
      todPct: "2.00",
    });

    expect(await codeOf(getCommissionPreview(openApplication()))).toBe("not_closed");
  });

  it("records it again over the seeded one, the server working out every figure", async () => {
    const applicationId = closedApplication();
    expect((await getLiveCommission(applicationId)).status).toBe("calculated");

    const saved = await recordCommission(applicationId, { body: ROUND, idempotencyKey: key() });

    expect(saved).toMatchObject({
      status: "calculated",
      commissionBase: "102000.00",
      commissionAmount: "5100.00",
      todBase: "102000.00",
      todAmount: "2040.00",
      total: "7140.00",
    });
    expect(mockDb.commissions).toHaveLength(1);
  });

  it("refuses fittings above the cost, on the field", async () => {
    const error = await recordCommission(closedApplication(), {
      body: { ...ROUND, gi_fitting: "200000" },
      idempotencyKey: key(),
    }).catch((caught: unknown) => caught);
    expect(readFieldErrors(error)?.gi_fitting).toMatch(/more than the cost/);
  });

  it("has no rate once the scheme's rate is retired before the full-FP date", async () => {
    const applicationId = closedApplication();
    const closedOn = mockApplications().find(
      (item) => item.id === applicationId,
    )?.full_fp_received_on;
    if (closedOn == null) throw new Error("The closed application has no full-FP date");
    // A 0% scheme-wide rate from that day retires the 5% one.
    await addCommissionRate({
      body: {
        scheme: "GGRC",
        system_type: null,
        partner_type: null,
        partner_id: null,
        commission_pct: "0",
        tod_pct: "0",
        effective_from: closedOn,
      },
      idempotencyKey: key(),
    });

    expect((await getCommissionPreview(applicationId)).commissionPct).toBeNull();
    expect(
      await codeOf(recordCommission(applicationId, { body: ROUND, idempotencyKey: key() })),
    ).toBe("no_rate");
  });
});

describe("[SUBS-017] Accounts — the contract", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("approves, then pays; refuses the recorder's own approval, a return without a remark, a future payment", async () => {
    writeMockRole("admin");
    const applicationId = closedApplication();
    const mine = await recordCommission(applicationId, { body: ROUND, idempotencyKey: key() });
    expect(
      await codeOf(
        decideCommission(mine.id, "approve", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("own_decision");

    writeMockRole("account_manager");
    expect(
      await codeOf(
        decideCommission(mine.id, "return", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("remark_required");
    const approved = await decideCommission(mine.id, "approve", {
      body: { remark: null },
      idempotencyKey: key(),
    });
    expect(approved.status).toBe("approved");

    const tomorrow = shiftCalendarDay(todayInIndia(), 1);
    expect(
      await codeOf(
        payCommission(mine.id, {
          body: { paid_on: tomorrow, payment_reference: "UTR1" },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("validation_error");
    const paid = await payCommission(mine.id, {
      body: { paid_on: todayInIndia(), payment_reference: "NEFT UTR 4471" },
      idempotencyKey: key(),
    });
    expect(paid).toMatchObject({ status: "paid", paymentReference: "NEFT UTR 4471" });

    writeMockRole("admin");
    expect(
      await codeOf(recordCommission(applicationId, { body: ROUND, idempotencyKey: key() })),
    ).toBe("commission_exists");
  });

  it("refuses a field officer", async () => {
    writeMockRole("employee");
    expect(
      await codeOf(
        decideCommission("anything", "approve", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("forbidden");
  });
});

describe("[SUBS-018] Commission rates — the contract", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("lists a scheme's rates newest first, adds one, and refuses the same scope on the same day", async () => {
    writeMockRole("admin");
    const before = await listCommissionRates("GGRC");
    expect(before.map((rate) => rate.effectiveFrom)).toEqual([
      "2026-04-01",
      "2026-04-01",
      "2025-04-01",
    ]);

    const body = {
      scheme: "GGRC",
      system_type: "drip" as const,
      partner_type: "sub_dealer" as const,
      partner_id: null,
      commission_pct: "5.5",
      tod_pct: "2",
      effective_from: "2026-10-01",
    };
    const added = await addCommissionRate({ body, idempotencyKey: key() });
    expect(added).toMatchObject({ commissionPct: "5.50", systemType: "drip" });
    expect(await codeOf(addCommissionRate({ body, idempotencyKey: key() }))).toBe("rate_exists");

    writeMockRole("account_manager");
    expect(await codeOf(addCommissionRate({ body, idempotencyKey: key() }))).toBe("forbidden");
  });
});

describe("[SUBS-016] Stage 18 — the screen", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("shows the recorded commission, then records it again with the figures worked out as typed", async () => {
    const user = show(<ApplicationDetail applicationId={closedApplication()} />);

    // The card replaces its skeleton once the commission loads: find it after that.
    await user.click(await screen.findByRole("button", { name: "Record it again" }));
    const card = screen.getByRole("region", { name: /Dealer commission/ });
    expect(within(card).getByText("To approve")).toBeInTheDocument();

    const form = await within(card).findByRole("form", { name: "Record the commission again" });
    const gi = within(form).getByLabelText("GI fittings");
    const pvc = within(form).getByLabelText("PVC and HDPE fittings");
    await user.clear(gi);
    await user.type(gi, "3000");
    await user.clear(pvc);
    await user.type(pvc, "1570.30");
    const working = within(card).getByLabelText("The commission as typed");
    expect(within(working).getByText("₹1,02,000.00")).toBeInTheDocument();
    expect(within(working).getByText("₹7,140.00")).toBeInTheDocument();

    await user.click(within(form).getByRole("button", { name: "Record it again" }));
    expect(await screen.findByText("Commission recorded again")).toBeInTheDocument();
    const recorded = await within(card).findByLabelText("The commission");
    expect(within(recorded).getByText("₹7,140.00")).toBeInTheDocument();
  });

  it("names a fitting problem on its field before sending", async () => {
    const user = show(<ApplicationDetail applicationId={closedApplication()} />);
    await user.click(await screen.findByRole("button", { name: "Record it again" }));
    const card = screen.getByRole("region", { name: /Dealer commission/ });
    const form = await within(card).findByRole("form", { name: "Record the commission again" });
    const gi = within(form).getByLabelText("GI fittings");
    await user.clear(gi);
    await user.type(gi, "200000");
    await user.click(within(form).getByRole("button", { name: "Record it again" }));

    expect(await within(form).findByText(/more than the cost before GST/)).toBeInTheDocument();
    expect(gi).toHaveAttribute("aria-invalid", "true");
  });

  it("says when no rate is in force, with the way to add one", async () => {
    mockDb.commissionRates = [];
    mockDb.commissions = [];
    show(<ApplicationDetail applicationId={closedApplication()} />);

    expect(
      await screen.findByText(/No commission rate is in force for Babra Farm Supplies/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Commission rates/ })).toHaveAttribute(
      "href",
      "/subsidy-masters?table=commission",
    );
  });

  it("shows nothing on an application still open", async () => {
    show(<ApplicationDetail applicationId={openApplication()} />);
    await screen.findByRole("heading", { level: 2 });
    await waitFor(() => {
      expect(screen.queryByRole("region", { name: /Dealer commission/ })).not.toBeInTheDocument();
    });
  });
});

describe("[SUBS-017] Dealer commissions — the screen", () => {
  beforeEach(() => {
    signInAs("account_manager");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("approves what waits, then records its payment", async () => {
    const user = show(<CommissionsList />);
    const list = await screen.findByRole("list", { name: "Dealer commissions" });
    // The actions appear once the session says what this role may do.
    await user.click(await within(list).findByRole("button", { name: /^Approve the commission/ }));
    const approve = await screen.findByRole("dialog", { name: "Approve the commission?" });
    await user.click(within(approve).getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Commission approved")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "To pay" }));
    const toPay = await screen.findByRole("list", { name: "Dealer commissions" });
    await user.click(await within(toPay).findByRole("button", { name: /^Record the payment/ }));
    const pay = await screen.findByRole("dialog", { name: "Record the payment" });
    await user.click(within(pay).getByRole("button", { name: "Record payment" }));
    expect(await within(pay).findByText("Give the UTR or cheque number.")).toBeInTheDocument();
    await user.type(within(pay).getByLabelText("Payment reference"), "NEFT UTR 4471");
    await user.click(within(pay).getByRole("button", { name: "Record payment" }));

    expect(await screen.findByText("Payment recorded")).toBeInTheDocument();
    expect(mockDb.commissions?.[0]?.status).toBe("paid");
  });

  it("returns one with a remark", async () => {
    const user = show(<CommissionsList />);
    const list = await screen.findByRole("list", { name: "Dealer commissions" });
    await user.click(await within(list).findByRole("button", { name: /^Return the commission/ }));
    const dialog = await screen.findByRole("dialog", { name: "Return the commission?" });
    await user.click(within(dialog).getByRole("button", { name: "Return" }));
    expect(await within(dialog).findByText("Say why.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Why"), "GI fittings bill missing");
    await user.click(within(dialog).getByRole("button", { name: "Return" }));

    expect(await screen.findByText("Commission returned")).toBeInTheDocument();
    expect(mockDb.commissions?.[0]?.decision_remark).toBe("GI fittings bill missing");
  });

  it("says when nothing waits", async () => {
    mockDb.commissions = [];
    show(<CommissionsList />);
    expect(await screen.findByText("Nothing to approve")).toBeInTheDocument();
  });
});

describe("[SUBS-018] Commission rates — the screen", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("lists the rates with the one in force, and adds one", async () => {
    const user = show(<SubsidyMasters />, "?table=commission");
    const list = await screen.findByRole("list", { name: "Commission rates for GGRC" });
    expect(within(list).getAllByText("In force")).toHaveLength(2);
    expect(within(list).getByText("Superseded")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Add a rate" }));
    const dialog = await screen.findByRole("dialog", { name: "Add a commission rate" });
    await user.click(within(dialog).getByRole("button", { name: "Add rate" }));
    expect(await within(dialog).findAllByText("Enter a percentage, or 0.")).toHaveLength(2);
    await user.type(within(dialog).getByLabelText("Commission"), "5.5");
    await user.type(within(dialog).getByLabelText("TOD"), "2");
    await user.click(within(dialog).getByRole("button", { name: "Add rate" }));

    expect(await screen.findByText("Rate added")).toBeInTheDocument();
    expect(mockDb.commissionRates[0]?.commission_pct).toBe("5.50");
  });
});
