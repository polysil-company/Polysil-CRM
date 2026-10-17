import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  createCampaign,
  deleteCampaign,
  getCampaign,
  listCampaigns,
  patchCampaign,
} from "@/features/campaigns/api/campaigns.api";
import { listLeads } from "@/features/leads/api/leads.api";
import { LeadDetail } from "@/features/leads/components/lead-detail";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockCampaignId } from "@/mocks/data/campaigns";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { CampaignsPage } from "./campaigns-page";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

async function failureOf(
  call: Promise<unknown>,
): Promise<{ status: number | undefined; code: string | undefined }> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error)
    ? { status: error.status, code: error.code }
    : { status: undefined, code: undefined };
}

let keys = 0;
function key(): string {
  keys += 1;
  return `campaigns-test-${String(keys)}`;
}

/** The seeded fair, on every eighth lead. */
const FAIR = mockCampaignId(1);
/** The seeded switched-off dealer meet, which no lead names. */
const OLD_MEET = mockCampaignId(4);

function reset(role: Role = "admin"): void {
  resetMockDb();
  signInAs(role);
}

const listParams = {
  cursor: null,
  pageSize: 100,
  sort: "createdAt",
  order: "desc",
  q: "",
  stage: [],
  source: null,
  type: null,
  areas: [],
} as const;

describe("[MKT-005] Campaigns (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("lists campaigns for staff, with cost only for those who may see it", async () => {
    reset("admin");
    const all = await listCampaigns({ active: null, type: null, q: "" });
    expect(all.map((campaign) => campaign.name)).toContain("Krishi Mela Rajkot 2026");
    expect(all.find((campaign) => campaign.id === FAIR)?.costPlanned).toBe("150000.00");

    reset("employee");
    const officer = await listCampaigns({ active: true, type: null, q: "" });
    expect(officer.every((campaign) => campaign.costPlanned === null)).toBe(true);
    expect(officer.some((campaign) => campaign.id === OLD_MEET)).toBe(false);

    reset("dealer");
    expect((await failureOf(listCampaigns({ active: true, type: null, q: "" }))).status).toBe(403);
  });

  it("refuses a taken name, case ignored, and an end before the start", async () => {
    reset("admin");
    const body = {
      name: "krishi mela rajkot 2026",
      type: "agri_fair",
      territory_id: null,
      start_date: "2026-11-01",
      end_date: null,
      cost_planned: "1000",
      cost_actual: null,
      description: null,
    } as const;
    expect((await failureOf(createCampaign({ body, idempotencyKey: key() }))).code).toBe(
      "campaign_name_taken",
    );
    expect(
      (
        await failureOf(
          createCampaign({
            body: { ...body, name: "New fair", end_date: "2026-10-01" },
            idempotencyKey: key(),
          }),
        )
      ).status,
    ).toBe(422);
  });

  it("keeps a campaign that leads name, and deletes one nothing names", async () => {
    reset("admin");
    expect((await failureOf(deleteCampaign(FAIR, key()))).code).toBe("campaign_in_use");
    await deleteCampaign(OLD_MEET, key());
    expect(mockDb.campaigns.some((campaign) => campaign.id === OLD_MEET)).toBe(false);
  });

  it("sums a campaign's leads, wins and cost per lead", async () => {
    reset("admin");
    const fair = await getCampaign(FAIR);
    const named = mockDb.leads.filter(
      (lead) => lead.campaign_id === FAIR && lead.stage !== "merged",
    ).length;
    expect(fair.summary?.leads).toBe(named);
    expect(fair.summary?.costPerLead).toBe((150000 / named).toFixed(2));
  });
});

describe("[MKT-006] A campaign on a lead (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("filters leads by campaign, and by none", async () => {
    reset("admin");
    const withFair = await listLeads({ ...listParams, campaign: FAIR });
    expect(withFair.items.length).toBeGreaterThan(0);
    expect(withFair.items.every((lead) => lead.campaign?.id === FAIR)).toBe(true);
    const without = await listLeads({ ...listParams, campaign: "none" });
    expect(without.items.every((lead) => lead.campaign === null)).toBe(true);
  });

  it("refuses a switched-off campaign on a lead", async () => {
    reset("admin");
    await patchCampaign(FAIR, { body: { is_active: false }, idempotencyKey: key() });
    const lead = mockDb.leads.find((item) => item.campaign_id == null && item.stage === "new");
    if (lead === undefined) throw new Error("No open lead without a campaign");
    const response = await fetch(buildApiUrl(`/leads/${lead.id}`), {
      method: "PATCH",
      headers: { "content-type": "application/json", "idempotency-key": key() },
      body: JSON.stringify({ campaign_id: FAIR }),
    });
    expect(response.status).toBe(422);
  });
});

describe("[MKT-005] CampaignsPage", () => {
  afterEach(() => {
    reset();
  });

  function show(searchParams = ""): ReturnType<typeof userEvent.setup> {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <CampaignsPage />
        <Toaster />
      </>,
      { searchParams },
    );
    return user;
  }

  it("lists the running campaigns with their leads and cost", async () => {
    reset("admin");
    show();
    const list = await screen.findByRole("list", { name: "Campaigns" });
    expect(within(list).getByText("Krishi Mela Rajkot 2026")).toBeInTheDocument();
    expect(within(list).queryByText("Bhavnagar dealer meet 2025")).toBeNull();
    expect(within(list).getAllByText(/Planned|Spent/).length).toBeGreaterThan(0);
  });

  it("adds a campaign, refusing a taken name on its field", async () => {
    reset("admin");
    const user = show();
    await user.click(await screen.findByRole("button", { name: "New campaign" }));
    const form = await screen.findByRole("form", { name: "New campaign" });
    await user.click(within(form).getByRole("button", { name: "Add campaign" }));
    expect(await within(form).findByText(/Name it/)).toBeInTheDocument();
    expect(within(form).getByText("Choose what kind of campaign it is.")).toBeInTheDocument();

    await user.type(within(form).getByLabelText("Name"), "Krishi Mela Rajkot 2026");
    await user.click(within(form).getByLabelText("Kind"));
    await user.click(await screen.findByRole("option", { name: "Exhibition" }));
    await user.click(within(form).getByRole("button", { name: "Add campaign" }));
    expect(await within(form).findByText("Another campaign has this name.")).toBeInTheDocument();

    const name = within(form).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Junagadh drip expo");
    // After a refusal the button reads "Not saved" for a moment, then "Add campaign" again.
    await user.click(
      await within(form).findByRole("button", { name: "Add campaign" }, { timeout: 4000 }),
    );
    expect(await screen.findByText("Junagadh drip expo added")).toBeInTheDocument();
  });

  it("opens a campaign's summary, and offers to switch it off when it can't be deleted", async () => {
    reset("admin");
    const user = show(`?campaign=${FAIR}`);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("How it did")).toHaveTextContent("Cost per lead");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await user.click(await within(dialog).findByRole("button", { name: "Delete campaign" }));
    expect(await within(dialog).findByText(/Leads or QR codes name this campaign/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Switch off instead" }));
    expect(await screen.findByText("Krishi Mela Rajkot 2026 switched off")).toBeInTheDocument();
  });

  it("hides adding from someone who may not", async () => {
    reset("district_manager");
    show();
    await screen.findByRole("list", { name: "Campaigns" });
    expect(screen.queryByRole("button", { name: "New campaign" })).toBeNull();
  });
});

describe("[MKT-006] The campaign on a lead", () => {
  afterEach(() => {
    reset();
  });

  it("names it on the lead, and changes it from Edit", async () => {
    reset("admin");
    const lead = mockDb.leads.find(
      (item) => item.campaign_id === FAIR && ["new", "contacted"].includes(item.stage),
    );
    if (lead === undefined) throw new Error("No open lead on the fair");
    const patches: unknown[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "PATCH") {
        void request
          .clone()
          .json()
          .then((body) => patches.push(body));
      }
    });
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <LeadDetail leadId={lead.id} />
        <Toaster />
      </>,
    );
    expect(await screen.findByText(/Campaign: Krishi Mela Rajkot 2026/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByLabelText(/^Campaign/));
    await user.click(await screen.findByRole("option", { name: "None" }));
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Lead updated")).toBeInTheDocument();
    await waitFor(() => {
      expect(patches).toEqual([{ campaign_id: null }]);
    });
    server.events.removeAllListeners();
  });
});
