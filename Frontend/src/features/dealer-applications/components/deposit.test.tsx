import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  decideDealerApplication,
  getDealerApplication,
  listDealerApplications,
  recordDealerApplicationDeposit,
  relaxDealerApplicationDeposit,
} from "@/features/dealer-applications/api/dealer-applications.api";
import { uploadDocument } from "@/features/documents/api/documents.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { mockDealerApplications } from "@/mocks/handlers/dealer-applications";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DealerApplicationDetail } from "./dealer-application-detail";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), notFound: vi.fn() }));

let keys = 0;
function key(): string {
  keys += 1;
  return `deposit-${String(keys)}`;
}

/** A form with a file and a date, typed into by a user: slower than 5 s in jsdom. */
const LONG_FORM = { timeout: 20_000 };

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
  resetMockDb();
  writeMockRole("admin");
}

/** The seeded draft that still owes a dealer's deposit of 50,000. */
function owing(): string {
  const application = mockDealerApplications().find((item) => item.status === "draft");
  if (application === undefined) throw new Error("No draft application");
  return application.id;
}

function slip(): File {
  return new File([new Uint8Array(2048)], "pay-slip.pdf", { type: "application/pdf" });
}

async function uploadSlip(applicationId: string): Promise<string> {
  const uploaded = await uploadDocument({
    recordType: "dealer_application",
    recordId: applicationId,
    docType: "deposit_slip",
    name: null,
    file: slip(),
    idempotencyKey: key(),
  });
  return uploaded.id;
}

describe("[CHNL-007] The deposit (FS-071), through the API", () => {
  beforeEach(reset);
  afterEach(reset);

  it("says a deposit is due, and records it with its pay slip, never less than due", async () => {
    signInAs("district_manager");
    const id = owing();
    const rows = await listDealerApplications({ status: [], q: "", partnerType: null });
    expect(rows.find((row) => row.id === id)?.depositStatus).toBe("pending");
    expect((await getDealerApplication(id)).can.recordDeposit).toBe(true);

    const body = { amount: "50000", paid_on: todayInIndia(), reference: "UTR 1234", slip_id: "" };
    await expect(
      recordDealerApplicationDeposit({ applicationId: id, body, idempotencyKey: key() }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { slip_id: expect.any(String) } } });

    const slipId = await uploadSlip(id);
    await expect(
      recordDealerApplicationDeposit({
        applicationId: id,
        body: { ...body, amount: "40000", slip_id: slipId },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422, code: "deposit_short" });

    const paid = await recordDealerApplicationDeposit({
      applicationId: id,
      body: { ...body, slip_id: slipId },
      idempotencyKey: key(),
    });
    expect(paid.deposit).toMatchObject({
      status: "paid",
      paidAmount: "50000.00",
      reference: "UTR 1234",
      history: [{ kind: "payment", amount: "50000.00" }],
    });
  });

  it("lets only the roles the settings name lower or waive it, before a payment", async () => {
    const id = owing();
    signInAs("district_manager");
    await expect(
      relaxDealerApplicationDeposit({
        applicationId: id,
        body: { amount_due: "0", reason: "Old partner" },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 403, code: "not_your_relaxation" });

    signInAs("regional_manager");
    expect((await getDealerApplication(id)).can.relaxDeposit).toBe(true);
    await expect(
      relaxDealerApplicationDeposit({
        applicationId: id,
        body: { amount_due: "60000", reason: "More" },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422, code: "not_lower" });
    const waived = await relaxDealerApplicationDeposit({
      applicationId: id,
      body: { amount_due: "0", reason: "Took over an old partner's business" },
      idempotencyKey: key(),
    });
    expect(waived.deposit).toMatchObject({
      status: "waived",
      amountDue: "0.00",
      history: [{ kind: "relaxation", fromDue: "50000.00", to: "0.00" }],
    });
    expect(waived.can.recordDeposit).toBe(false);
  });

  it("keeps an approval waiting until the deposit is paid", async () => {
    const submitted = mockDealerApplications().find((item) => item.status === "submitted");
    if (submitted === undefined) throw new Error("No submitted application");
    submitted.deposit = {
      status: "pending",
      amount_set: "50000.00",
      amount_due: "50000.00",
      paid_amount: null,
      paid_on: null,
      reference: null,
      slip_id: null,
      history: [],
    };
    signInAs("state_manager");
    await expect(
      decideDealerApplication({
        applicationId: submitted.id,
        body: { decision: "approve", remark: null, parent_id: null, code: null },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 409, code: "deposit_pending" });
  });
});

describe("[CHNL-007] The deposit on an application's page (FS-071)", () => {
  beforeEach(reset);
  afterEach(reset);

  it("records the deposit with its pay slip", LONG_FORM, async () => {
    signInAs("district_manager");
    const user = show(<DealerApplicationDetail applicationId={owing()} />);

    expect(await screen.findByRole("heading", { name: "Deposit" })).toBeInTheDocument();
    expect(screen.getByText("Deposit due")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Record the deposit" }));
    const form = await screen.findByRole("form", { name: "Record the deposit" });
    expect(within(form).getByRole("textbox", { name: "Amount paid, in rupees" })).toHaveValue(
      "50000.00",
    );
    await user.click(within(form).getByRole("button", { name: "Record the deposit" }));
    expect(await within(form).findByText("Attach the pay slip.")).toBeInTheDocument();

    await user.upload(within(form).getByLabelText("Pay slip"), slip());
    await user.type(within(form).getByRole("textbox", { name: /Reference/ }), "UTR 1234");
    await user.click(within(form).getByRole("button", { name: "Record the deposit" }));

    expect(await screen.findByText("Deposit recorded")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Deposit paid")).toBeInTheDocument();
    });
    expect(screen.getByRole("list", { name: "Deposit history" })).toHaveTextContent(/Paid ₹50,000/);
  });

  it("waives it, for a role the settings name", LONG_FORM, async () => {
    signInAs("regional_manager");
    const user = show(<DealerApplicationDetail applicationId={owing()} />);

    await user.click(await screen.findByRole("button", { name: "Lower or waive it" }));
    const form = await screen.findByRole("form", { name: "Lower or waive the deposit" });
    await user.click(within(form).getByRole("button", { name: "Waive it" }));
    expect(await within(form).findByText("Say why it is lowered.")).toBeInTheDocument();
    await user.type(within(form).getByRole("textbox", { name: "Why" }), "Took over a business");
    await user.click(within(form).getByRole("button", { name: "Waive it" }));

    expect(await screen.findByText("Deposit waived", { selector: "[data-title]" })).toBeVisible();
  });
});
