import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  createDealerApplication,
  decideDealerApplication,
  getDealerApplication,
  listDealerApplications,
  patchDealerApplication,
  submitDealerApplication,
} from "@/features/dealer-applications/api/dealer-applications.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb, resetMockDb } from "@/mocks/db";
import { mockDealerApplications } from "@/mocks/handlers/dealer-applications";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DealerApplicationDetail } from "./dealer-application-detail";
import { DealerApplicationsList } from "./dealer-applications-list";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), notFound: vi.fn() }));

let keys = 0;
function key(): string {
  keys += 1;
  return `dealer-app-${String(keys)}`;
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

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

function seeded(status: string): string {
  const application = mockDealerApplications().find((item) => item.status === status);
  if (application === undefined) throw new Error(`No ${status} application`);
  return application.id;
}

function district(): string {
  const found = MOCK_TERRITORIES.find((territory) => territory.level === "district");
  if (found === undefined) throw new Error("No district");
  return found.id;
}

describe("[CHNL-007] Dealer applications, through the API", () => {
  beforeEach(reset);
  afterEach(reset);

  it("starts one with its link, and refuses a mobile in use or already applying", async () => {
    signInAs("admin");
    const started = await createDealerApplication({
      body: {
        firm_name: "Jay Ambe Agro",
        contact_name: "Rakesh Dabhi",
        mobile: "+919812300011",
        territory_id: district(),
      },
      idempotencyKey: key(),
    });
    expect(started.status).toBe("draft");
    expect(started.applyUrl).toMatch(/\/dealer-apply\/apply-/);
    expect(started.missing).toContain("pan_card");
    // read again, the link isn't there: the backend keeps only its hash
    expect((await getDealerApplication(started.id)).applyUrl).toBeNull();

    await expect(
      createDealerApplication({
        body: {
          firm_name: "Jay Ambe Agro",
          contact_name: "Rakesh Dabhi",
          mobile: "+919812300011",
          territory_id: district(),
        },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 409, code: "application_open" });

    const partnerMobile = mockDb.partners.find((partner) => partner.mobile !== null)?.mobile;
    await expect(
      createDealerApplication({
        body: {
          firm_name: "Someone",
          contact_name: "Someone",
          mobile: `+${partnerMobile ?? ""}`,
          territory_id: district(),
        },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 409, code: "mobile_in_use" });
  });

  it("won't submit what is missing, and checks the PAN inside the GSTIN", async () => {
    signInAs("admin");
    const id = seeded("draft");
    await expect(
      submitDealerApplication({ applicationId: id, idempotencyKey: key() }),
    ).rejects.toMatchObject({
      status: 422,
      code: "application_incomplete",
      details: { fields: { pan: "required", pan_card: "required" } },
    });

    await expect(
      patchDealerApplication({
        applicationId: id,
        body: { gstin: "24AAACP1234F1Z5", pan: "ABCDE1234F" },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { pan: expect.any(String) } } });

    const filled = await patchDealerApplication({
      applicationId: id,
      body: { firm_type: "partnership", gstin: "24aaacp1234f1z5", pan: "AAACP1234F" },
      idempotencyKey: key(),
    });
    expect(filled.gstin).toBe("24AAACP1234F1Z5");
    expect(filled.missing).not.toContain("firm_type");
  });

  it("lets a State Manager decide one a colleague started, never an employee", async () => {
    signInAs("employee");
    const id = seeded("submitted");
    expect((await getDealerApplication(id)).can.decide).toBe(false);
    await expect(
      decideDealerApplication({
        applicationId: id,
        body: { decision: "approve", remark: null, parent_id: null, code: null },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 403 });

    signInAs("state_manager");
    await expect(
      decideDealerApplication({
        applicationId: id,
        body: { decision: "return", remark: null, parent_id: null, code: null },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { remark: expect.any(String) } } });
    const approved = await decideDealerApplication({
      applicationId: id,
      body: { decision: "approve", remark: null, parent_id: null, code: null },
      idempotencyKey: key(),
    });
    expect(approved.status).toBe("approved");
    expect(mockDb.partners.find((partner) => partner.id === approved.partnerId)).toMatchObject({
      name: "Patel Agro",
      partner_type: "dealer",
    });
  });

  it("filters by status", async () => {
    signInAs("admin");
    const rows = await listDealerApplications({ status: ["returned"], q: "" });
    expect(rows.map((row) => row.status)).toEqual(["returned"]);
  });
});

describe("[CHNL-007] DealerApplicationsList", () => {
  beforeEach(reset);
  afterEach(reset);

  it("lists them, and starts one with the link to send", async () => {
    signInAs("district_manager");
    const user = show(<DealerApplicationsList />);

    const list = await screen.findByRole("list", { name: "Dealer applications" });
    expect(
      within(list).getByRole("link", { name: /^Patel Agro, Jignesh Patel, Submitted/ }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Start an application" }));
    const form = await screen.findByRole("form", { name: "Start a dealer application" });
    await user.click(within(form).getByRole("button", { name: "Start the application" }));
    expect(await within(form).findByText("Enter the firm's name.")).toBeInTheDocument();

    await user.type(within(form).getByRole("textbox", { name: "Firm" }), "Jay Ambe Agro");
    await user.type(within(form).getByRole("textbox", { name: "Contact person" }), "Rakesh");
    await user.type(within(form).getByRole("textbox", { name: "Mobile" }), "9812300011");
    await user.type(within(form).getByRole("combobox", { name: "Area" }), "Raj");
    await user.click((await screen.findAllByRole("option"))[0] ?? document.body);
    await user.click(within(form).getByRole("button", { name: "Start the application" }));

    const dialog = await screen.findByRole("dialog", { name: "Application started" });
    expect(within(dialog).getByText(/\/dealer-apply\/apply-/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Share on WhatsApp" })).toHaveAttribute(
      "href",
      expect.stringContaining("https://wa.me/919812300011"),
    );
    expect(within(dialog).getByRole("link", { name: "Open the application" })).toBeInTheDocument();
  });
});

describe("[CHNL-007] DealerApplicationDetail", () => {
  beforeEach(reset);
  afterEach(reset);

  it("says what is still missing, and saves what staff fill in", async () => {
    signInAs("district_manager");
    const user = show(<DealerApplicationDetail applicationId={seeded("draft")} />);

    expect(await screen.findByText("Still needed before it can be submitted")).toBeInTheDocument();
    expect(screen.getByText(/PAN card \(document\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit details" }));
    const form = await screen.findByRole("form", { name: "Edit the application" });
    await user.type(within(form).getByRole("textbox", { name: "PAN" }), "abcde1234f");
    await user.type(within(form).getByRole("textbox", { name: "Pincode" }), "36000");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await within(form).findByText("Six digits.")).toBeInTheDocument();

    await user.type(within(form).getByRole("textbox", { name: "Pincode" }), "1");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Application updated")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("ABCDE1234F")).toBeInTheDocument();
    });
  });

  it("lets a State Manager approve a submitted one, and then links the dealer", async () => {
    signInAs("state_manager");
    const user = show(<DealerApplicationDetail applicationId={seeded("submitted")} />);

    await user.click(await screen.findByRole("button", { name: "Decide" }));
    const form = await screen.findByRole("form", { name: "Decide the application" });
    await user.click(within(form).getByRole("radio", { name: "Reject" }));
    await user.click(within(form).getByRole("button", { name: "Reject" }));
    expect(await within(form).findByText("Say why it is rejected.")).toBeInTheDocument();

    await user.click(within(form).getByRole("radio", { name: "Approve" }));
    await user.click(within(form).getByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText("Approved: the dealer and its login are added"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the dealer" })).toHaveAttribute(
      "href",
      expect.stringMatching(/^\/partners\//),
    );
    expect(screen.queryByRole("button", { name: "Decide" })).not.toBeInTheDocument();
  });

  it("shows the manager's remark on a returned one, and withdraws it", async () => {
    signInAs("district_manager");
    const user = show(<DealerApplicationDetail applicationId={seeded("returned")} />);

    expect(await screen.findByText(/The cancelled cheque is unreadable/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Withdraw…" }));
    const form = await screen.findByRole("form", { name: "Withdraw the application" });
    await user.type(within(form).getByRole("textbox", { name: "Why" }), "Not interested now");
    await user.click(within(form).getByRole("button", { name: "Withdraw" }));

    expect(await screen.findByText("Application withdrawn")).toBeInTheDocument();
    expect(await screen.findByText("Not interested now")).toBeInTheDocument();
  });
});
