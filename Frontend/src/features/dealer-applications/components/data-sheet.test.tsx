import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  createDealerApplication,
  getDealerApplication,
  listDealerApplications,
  patchDealerApplication,
} from "@/features/dealer-applications/api/dealer-applications.api";
import { patchSettings } from "@/features/settings/api/settings.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { resetMockDb } from "@/mocks/db";
import { mockDealerApplications } from "@/mocks/handlers/dealer-applications";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DealerApplicationDetail } from "./dealer-application-detail";
import { DealerApplicationsList } from "./dealer-applications-list";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), notFound: vi.fn() }));

let keys = 0;
function key(): string {
  keys += 1;
  return `data-sheet-${String(keys)}`;
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

/** A form with tables typed into by a user: slower than the default 5 s in jsdom. */
const LONG_FORM = { timeout: 20_000 };

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
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

describe("[CHNL-007] Distributor applications (FS-071), through the API", () => {
  beforeEach(reset);
  afterEach(reset);

  it("starts a distributor's, and filters the list by type", async () => {
    signInAs("admin");
    const started = await createDealerApplication({
      body: {
        firm_name: "Shree Distributors",
        contact_name: "Mahesh Joshi",
        mobile: "9812300077",
        territory_id: district(),
        partner_type: "distributor",
      },
      idempotencyKey: key(),
    });
    expect(started.partnerType).toBe("distributor");

    const distributors = await listDealerApplications({
      status: [],
      q: "",
      partnerType: "distributor",
    });
    expect(distributors.map((row) => row.firmName)).toEqual(["Shree Distributors"]);
    const dealers = await listDealerApplications({ status: [], q: "", partnerType: "dealer" });
    expect(dealers.every((row) => row.partnerType === "dealer")).toBe(true);
  });

  it("saves the data sheet with its tables, and refuses an amount out of shape", async () => {
    signInAs("admin");
    const id = seeded("draft");
    await expect(
      patchDealerApplication({
        applicationId: id,
        body: { working_capital: [{ facility: "Own funds", amount_lakhs: "12.345" }] },
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422 });

    const saved = await patchDealerApplication({
      applicationId: id,
      body: {
        working_capital: [{ facility: "Own funds", amount_lakhs: "12.5" }],
        other_sources_lakhs: "2.25",
        area_unit: "sq_m",
        office_area: "120",
        manpower: [
          {
            category: "Plumbers",
            qualification: null,
            work_type: "Drip laying",
            experience_years: 4,
            people: 3,
          },
        ],
      },
      idempotencyKey: key(),
    });
    expect(saved.dataSheet).toMatchObject({
      workingCapital: [{ facility: "Own funds", amountLakhs: "12.5" }],
      workingCapitalTotalLakhs: "14.75",
      areaUnit: "sq_m",
      officeArea: "120",
      manpower: [{ category: "Plumbers", people: 3, workType: "Drip laying" }],
    });
  });

  it("asks for the extra fields the company settings require of the type", async () => {
    signInAs("admin");
    const id = seeded("draft");
    expect((await getDealerApplication(id)).missing).not.toContain("telephone");
    await patchSettings({ values: { dealer_application_required: ["telephone"] } });
    expect((await getDealerApplication(id)).missing).toContain("telephone");
  });
});

describe("[CHNL-007] The data sheet and the type on the screens (FS-071)", () => {
  beforeEach(reset);
  afterEach(reset);

  it("starts a distributor's application and lists it with its type", async () => {
    signInAs("district_manager");
    const user = show(<DealerApplicationsList />);

    await user.click(await screen.findByRole("button", { name: "Start an application" }));
    const form = await screen.findByRole("form", { name: "Start an application" });
    await user.click(within(form).getByRole("radio", { name: "Distributor" }));
    await user.type(within(form).getByRole("textbox", { name: "Firm" }), "Shree Distributors");
    await user.type(within(form).getByRole("textbox", { name: "Contact person" }), "Mahesh");
    await user.type(within(form).getByRole("textbox", { name: "Mobile" }), "9812300078");
    await user.type(within(form).getByRole("combobox", { name: "Area" }), "Raj");
    await user.click((await screen.findAllByRole("option"))[0] ?? document.body);
    await user.click(within(form).getByRole("button", { name: "Start the application" }));

    await screen.findByRole("dialog", { name: "Application started" });
    expect(mockDealerApplications()[0]).toMatchObject({
      firm_name: "Shree Distributors",
      partner_type: "distributor",
    });
  });

  it(
    "fills in the tables, names the row at fault, and shows the sheet once saved",
    LONG_FORM,
    async () => {
      signInAs("district_manager");
      const user = show(<DealerApplicationDetail applicationId={seeded("draft")} />);

      expect(await screen.findByRole("heading", { name: "Data sheet" })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Edit details" }));
      const form = await screen.findByRole("form", { name: "Edit the application" });
      await user.click(within(form).getByRole("button", { name: "Add a facility" }));
      await user.type(within(form).getByRole("textbox", { name: "Facility 1" }), "Own funds");
      await user.type(within(form).getByRole("textbox", { name: "Amount, in lakhs" }), "12.345");
      await user.click(within(form).getByRole("button", { name: "Save changes" }));
      expect(await within(form).findByText(/Row 1: the amount in lakhs/)).toBeInTheDocument();

      const amount = within(form).getByRole("textbox", { name: "Amount, in lakhs" });
      await user.clear(amount);
      await user.type(amount, "12.5");
      await user.click(within(form).getByRole("button", { name: "Add a group of people" }));
      await user.type(within(form).getByRole("textbox", { name: "Group 1" }), "Plumbers");
      await user.type(within(form).getByRole("textbox", { name: "How many" }), "3");
      await user.click(within(form).getByRole("button", { name: "Save changes" }));

      expect(await screen.findByText("Application updated")).toBeInTheDocument();
      await waitFor(() => {
        expect(screen.getByText("12.5 lakhs")).toBeInTheDocument();
      });
      expect(screen.getByText(/3 × Plumbers/)).toBeInTheDocument();
    },
  );

  it("approves a distributor directly under Polysil, with no distributor to pick", async () => {
    const submitted = mockDealerApplications().find((item) => item.status === "submitted");
    if (submitted === undefined) throw new Error("No submitted application");
    submitted.partner_type = "distributor";
    signInAs("regional_manager");
    const user = show(<DealerApplicationDetail applicationId={submitted.id} />);

    expect(await screen.findByText("Distributor")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Decide" }));
    const form = await screen.findByRole("form", { name: "Decide the application" });
    expect(
      within(form).getByText("A distributor sits directly under Polysil."),
    ).toBeInTheDocument();
    expect(within(form).queryByLabelText(/Under a distributor/)).not.toBeInTheDocument();
    expect(within(form).getByText(/DIST-GJ-0003/)).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText("Approved: the distributor and its login are added"),
    ).toBeInTheDocument();
  });
});
