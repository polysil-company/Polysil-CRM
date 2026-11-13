import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { listSettings, patchSettings } from "@/features/settings/api/settings.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { CompanySettings } from "./company-settings";

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

function valueOf(key: string): unknown {
  return mockDb.settings?.find((setting) => setting.key === key)?.value;
}

describe("[ADMN-007] Company settings, through the API", () => {
  afterEach(reset);

  it("reads every setting with its kind, and changes one within its rule", async () => {
    signInAs("admin");
    const settings = await listSettings();
    expect(settings.find((item) => item.key === "complaint_reopen_days")).toMatchObject({
      kind: "int",
      value: 30,
      min: 1,
      max: 365,
    });

    const saved = await patchSettings({ values: { complaint_reopen_days: 15 } });
    expect(saved.find((item) => item.key === "complaint_reopen_days")?.value).toBe(15);
    await expect(patchSettings({ values: { complaint_reopen_days: 400 } })).rejects.toMatchObject({
      status: 422,
      details: { fields: { complaint_reopen_days: expect.any(String) } },
    });

    signInAs("employee");
    await expect(patchSettings({ values: { complaint_reopen_max: 3 } })).rejects.toMatchObject({
      status: 403,
    });
  });
});

describe("[ADMN-007] CompanySettings", () => {
  afterEach(reset);

  it("saves a number, a choice and the roles together", async () => {
    signInAs("admin");
    const user = show(<CompanySettings />);

    const days = await screen.findByLabelText("Days to reopen a complaint");
    await user.clear(days);
    await user.type(days, "400");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("At most 365.")).toBeInTheDocument();

    await user.clear(days);
    await user.type(days, "15");
    await user.click(screen.getByRole("radio", { name: "Only when its value rises" }));
    const roles = await screen.findByRole("group", { name: "Who may reopen a complaint" });
    await user.click(await within(roles).findByRole("checkbox", { name: "State Manager" }));
    expect(screen.getByText("3 changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Settings saved")).toBeInTheDocument();
    expect(valueOf("complaint_reopen_days")).toBe(15);
    expect(valueOf("order_amend_reapproval")).toBe("value_rises");
    expect(valueOf("complaint_reopen_roles")).toEqual(["qc_manager", "support", "state_manager"]);
  });

  it("keeps an approval chain in the order it's ticked, and says so", async () => {
    signInAs("admin");
    const user = show(<CompanySettings />);

    expect(await screen.findByRole("heading", { name: "Orders", level: 2 })).toBeInTheDocument();
    expect(
      screen.getByText("Changing this recalculates reports and targets for every month."),
    ).toBeInTheDocument();
    const chain = await screen.findByRole("group", { name: "Who approves a replacement order" });
    expect(
      await screen.findByText(
        /In this order: State Manager, then Regional Manager, then MD \/ CEO\./,
      ),
    ).toBeInTheDocument();
    const regional = await within(chain).findByRole("checkbox", { name: "Regional Manager" });
    await user.click(regional);
    await user.click(regional);
    expect(
      screen.getByText(/In this order: State Manager, then MD \/ CEO, then Regional Manager\./),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Setting saved")).toBeInTheDocument();
    expect(valueOf("replacement_approval_roles")).toEqual([
      "state_manager",
      "md_ceo",
      "regional_manager",
    ]);
  });

  it("shows the values to someone who may not change them", async () => {
    signInAs("employee");
    show(<CompanySettings />);

    expect(await screen.findByText("Re-approving an amended order")).toBeInTheDocument();
    expect(screen.getByText("Always")).toBeInTheDocument();
    expect(screen.getByText(/Only administrators of masters change them/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("QC Manager, Support")).toBeInTheDocument();
    });
    expect(
      screen.getByText("State Manager, then Regional Manager, then MD / CEO"),
    ).toBeInTheDocument();
    expect(screen.getByText("50,000")).toBeInTheDocument();
  });

  it("draws a setting it doesn't know from its kind, four rising bands", async () => {
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/settings"), () =>
        HttpResponse.json({
          data: [
            {
              key: "payment_ageing_bands",
              kind: "bands",
              value: [0, 30, 60, 90],
              allowed: null,
              min: null,
              max: null,
              description: "Where the ageing buckets start, in days.",
              updated_at: "2026-10-01T04:30:00.000Z",
            },
          ],
        }),
      ),
    );
    const user = show(<CompanySettings />);

    expect(await screen.findByRole("heading", { name: "Other", level: 2 })).toBeInTheDocument();
    const second = await screen.findByLabelText("Payment ageing bands, band 2");
    await user.clear(second);
    await user.type(second, "0");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Each one more than the one before.")).toBeInTheDocument();
  });
});

describe("[QUOT-015] The GST slabs on offer", () => {
  afterEach(reset);

  it("takes slabs in force, at least one, none twice", async () => {
    signInAs("admin");
    const settings = await listSettings();
    expect(settings.find((item) => item.key === "gst_slab_choices")).toMatchObject({
      kind: "slabs",
      value: ["0", "5", "18", "40"],
    });
    await expect(patchSettings({ values: { gst_slab_choices: ["5", "7"] } })).rejects.toMatchObject(
      { status: 422 },
    );
    await expect(
      patchSettings({ values: { gst_slab_choices: ["5", "5.0"] } }),
    ).rejects.toMatchObject({ status: 422 });
    await expect(patchSettings({ values: { gst_slab_choices: [] } })).rejects.toMatchObject({
      status: 422,
    });
  });

  it("ticks the slabs an item may be set to, lowest first", async () => {
    signInAs("admin");
    const user = show(<CompanySettings />);

    const slabs = await screen.findByRole("group", {
      name: "GST slabs an item or a charge can be set to",
    });
    expect(within(slabs).getByRole("checkbox", { name: "40%" })).toBeChecked();
    await user.click(within(slabs).getByRole("checkbox", { name: "0%" }));
    await user.click(within(slabs).getByRole("checkbox", { name: "12%" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Settings saved")).toBeInTheDocument();
    expect(valueOf("gst_slab_choices")).toEqual(["5", "12", "18", "40"]);
  });

  it("needs at least one slab", async () => {
    signInAs("admin");
    const user = show(<CompanySettings />);

    const slabs = await screen.findByRole("group", {
      name: "GST slabs an item or a charge can be set to",
    });
    for (const name of ["0%", "5%", "18%", "40%"]) {
      await user.click(within(slabs).getByRole("checkbox", { name }));
    }
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Choose at least one slab.")).toBeInTheDocument();
  });
});

describe("[ADMN-007] The application settings (FS-071): some of a list, and staff roles", () => {
  afterEach(reset);

  it("checks a set against its list and staff roles for at least one", async () => {
    signInAs("admin");
    const settings = await listSettings();
    expect(settings.find((item) => item.key === "dealer_application_required")).toMatchObject({
      kind: "set",
      value: [],
    });
    expect(settings.find((item) => item.key === "deposit_relaxation_roles")).toMatchObject({
      kind: "staff_roles",
      value: ["regional_manager", "md_ceo"],
    });
    await expect(
      patchSettings({ values: { dealer_application_required: ["email", "pan_number"] } }),
    ).rejects.toMatchObject({ status: 422 });
    await expect(patchSettings({ values: { deposit_relaxation_roles: [] } })).rejects.toMatchObject(
      { status: 422 },
    );
    await expect(
      patchSettings({ values: { deposit_relaxation_roles: ["dealer"] } }),
    ).rejects.toMatchObject({ status: 422 });
  });

  it("ticks the fields an application needs, and who decides, under their own section", async () => {
    signInAs("admin");
    const user = show(<CompanySettings />);

    expect(
      await screen.findByRole("heading", {
        name: "Dealer and distributor applications",
        level: 2,
      }),
    ).toBeInTheDocument();
    const required = await screen.findByRole("group", {
      name: "What a dealer application must have",
    });
    await user.click(within(required).getByRole("checkbox", { name: "Shop photo" }));
    await user.click(within(required).getByRole("checkbox", { name: "Telephone" }));
    const deciders = await screen.findByRole("group", {
      name: "Who decides a distributor application",
    });
    await user.click(await within(deciders).findByRole("checkbox", { name: "State Manager" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Settings saved")).toBeInTheDocument();
    // In the list's own order, whatever order they were ticked in.
    expect(valueOf("dealer_application_required")).toEqual(["telephone", "shop_photo"]);
    expect(valueOf("distributor_application_deciders")).toEqual([
      "regional_manager",
      "md_ceo",
      "admin_sales",
      "state_manager",
    ]);
  });

  it("needs at least one role to decide", async () => {
    signInAs("admin");
    const user = show(<CompanySettings />);

    const relaxers = await screen.findByRole("group", {
      name: "Who may lower or waive a deposit",
    });
    await user.click(await within(relaxers).findByRole("checkbox", { name: "Regional Manager" }));
    await user.click(within(relaxers).getByRole("checkbox", { name: "MD / CEO" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Choose at least one role.")).toBeInTheDocument();
  });

  it("shows a kind it doesn't know as text, and the rest of the page still works", async () => {
    signInAs("admin");
    server.use(
      http.get(buildApiUrl("/settings"), () =>
        HttpResponse.json({
          data: [
            {
              key: "holiday_calendar",
              kind: "calendar",
              value: { from: "2026-11-01" },
              allowed: null,
              min: null,
              max: null,
              description: "A kind added after this screen.",
              updated_at: "2026-10-01T04:30:00.000Z",
            },
            {
              key: "complaint_reopen_max",
              kind: "int",
              value: 2,
              allowed: null,
              min: 1,
              max: 10,
              description: "How many times one complaint may be reopened.",
              updated_at: "2026-10-01T04:30:00.000Z",
            },
          ],
        }),
      ),
    );
    show(<CompanySettings />);

    expect(await screen.findByText("Holiday calendar")).toBeInTheDocument();
    expect(screen.getByText('{"from":"2026-11-01"}')).toBeInTheDocument();
    expect(await screen.findByLabelText("Times a complaint can be reopened")).toHaveValue("2");
  });
});
