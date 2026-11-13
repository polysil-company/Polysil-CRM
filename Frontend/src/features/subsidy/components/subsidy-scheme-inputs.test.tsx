import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { createScheme } from "@/features/subsidy/api/subsidy-schemes.api";
import { calculateResponseSchema, type SystemConfig } from "@/features/subsidy/api/subsidy.schemas";
import { emptyDraft, planCalculation } from "@/features/subsidy/lib/calculator-draft";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockStateTerritoryId } from "@/mocks/data/subsidy-schemes";
import { resetMockDb } from "@/mocks/db";
import { calculate } from "@/mocks/handlers/subsidy";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { SubsidyCalculator } from "./subsidy-calculator";

const SETTLE = { timeout: 3000 };

function system(overrides: Partial<SystemConfig>): SystemConfig {
  return {
    systemType: "drip",
    hasHeadUnit: true,
    supportsGroup: false,
    cropCountMax: 1,
    formulaVersion: "v1",
    sprinklerAreas: null,
    inputs: [],
    unknownInputs: [],
    spacingLabels: [],
    ...overrides,
  };
}

function designed(): ReturnType<typeof emptyDraft> {
  const draft = emptyDraft("drip");
  const crop = draft.crops[0];
  if (crop === undefined) throw new Error("No crop block");
  return { ...draft, crops: [{ ...crop, area: "1.02", lateralSpacing: "5" }] };
}

describe("[SUBS-002] The scheme's inputs in the request", () => {
  it("sends none of them for a scheme that asks for none", () => {
    const plan = planCalculation(designed(), system({}));
    expect(plan.request).not.toBeNull();
    expect(plan.request).not.toHaveProperty("guided_cost");
    expect(plan.request).not.toHaveProperty("pipe_size_mm");
  });

  it("waits for AP drip's guided cost and fittings amount, then sends them", () => {
    const ap = system({ inputs: ["guided_cost", "fittings_amount"] });
    const draft = designed();
    expect(planCalculation(draft, ap).missing).toEqual(["guided_cost", "fittings_amount"]);

    const filled = {
      ...draft,
      scheme: { ...draft.scheme, guidedCost: "134367", fittingsAmount: "6502.55" },
    };
    expect(planCalculation(filled, ap).request).toMatchObject({
      guided_cost: "134367",
      fittings_amount: "6502.55",
    });

    const typo = {
      ...draft,
      scheme: { ...draft.scheme, guidedCost: "1,34,367", fittingsAmount: "0" },
    };
    expect(planCalculation(typo, ap).problems.guided_cost).toBe(
      "Enter the guided cost as a number, like 1.25.",
    );
  });

  it("sends RJ's spacing, filters and existing equipment; a spacing not in the list is a mistake", () => {
    const rj = system({
      inputs: [
        "spacing_label",
        "hydrocyclone_m3",
        "gravel_filter_m3",
        "head_unit_existing",
        "pvc_existing",
      ],
      spacingLabels: ["1.2 x 0.6 m"],
    });
    const draft = designed();
    expect(planCalculation(draft, rj).missing).toEqual(["spacing_label"]);

    const chosen = {
      ...draft,
      scheme: {
        ...draft.scheme,
        spacingLabel: "1.2 x 0.6 m",
        hydrocycloneM3: "20",
        pvcExisting: true,
      },
    };
    expect(planCalculation(chosen, rj).request).toMatchObject({
      spacing_label: "1.2 x 0.6 m",
      hydrocyclone_m3: 20,
      gravel_filter_m3: 0,
      head_unit_existing: false,
      pvc_existing: true,
    });

    const stale = { ...draft, scheme: { ...draft.scheme, spacingLabel: "9 x 9 m" } };
    expect(planCalculation(stale, rj).problems.spacing_label).toBe(
      "Choose one of the scheme's spacings.",
    );
  });

  it("asks a sprinkler for its set size when the scheme lists pipe_size_mm", () => {
    const sprinkler = system({
      systemType: "sprinkler",
      hasHeadUnit: false,
      sprinklerAreas: ["1.000"],
      inputs: ["pipe_size_mm"],
    });
    const draft = emptyDraft("sprinkler");
    const crop = draft.crops[0];
    if (crop === undefined) throw new Error("No crop block");
    const base = { ...draft, crops: [{ ...crop, area: "1.000", lateralSpacing: "12" }] };
    expect(planCalculation(base, sprinkler).missing).toEqual(["pipe_size_mm"]);
    const sized = { ...base, scheme: { ...base.scheme, pipeSizeMm: "75" } };
    expect(planCalculation(sized, sprinkler).request).toMatchObject({ pipe_size_mm: 75 });
  });
});

describe("[SUBS-002] An AP drip result", () => {
  it("reads null matrix ids and the state's half of the GST", () => {
    const wire = calculate({
      system_type: "drip",
      crops: [
        {
          crop: null,
          inter_crop: null,
          area: "1.02",
          crop_spacing: "",
          lateral_spacing: "5",
          lines: [],
        },
      ],
    });
    const parsed = calculateResponseSchema.parse({
      data: {
        ...wire,
        masters: { ...wire.masters, regular_matrix_id: null, seven_year_matrix_id: null },
        total: { blocks: { ...wire.total.blocks, gst_paid_by_state: "120.00" } },
      },
    });
    expect(parsed.guidedCost).toBe(true);
    expect(parsed.total.gst_paid_by_state).toBe("120.00");
    expect(parsed.total.fittings).toBe("0.00");
  });
});

describe("[SUBS-002] SubsidyCalculator · an AP drip quotation", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("asks for the portal's figures, then prints the guided cost and the state's GST", async () => {
    writeMockRole("admin");
    const state = mockStateTerritoryId("UP");
    if (state === null) throw new Error("No second state in the mock");
    await createScheme({
      body: {
        code: "AP",
        name: "AP Micro Irrigation Project",
        state_territory_id: state,
        template: "GGRC",
        systems: ["drip", "sprinkler"],
      },
      idempotencyKey: "calc-ap",
    });
    writeMockRole("employee");
    server.use(
      http.get(buildApiUrl("/auth/me"), () =>
        HttpResponse.json(mockMeFor("employee" satisfies Role)),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<SubsidyCalculator />);

    await user.click(await screen.findByRole("combobox", { name: "Scheme" }));
    await user.click(await screen.findByRole("option", { name: /^AP/ }));
    expect(
      await screen.findByText("The scheme's inputs", {}, { timeout: 5000 }),
    ).toBeInTheDocument();

    await user.type(await screen.findByRole("textbox", { name: /^Area/ }), "1.02");
    await user.type(screen.getByRole("textbox", { name: /^Lateral spacing/ }), "5");
    expect(
      await screen.findByText("Fill in the scheme's inputs to see the subsidy."),
    ).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /^Installation rate/ }), "5000");

    await user.type(
      screen.getByRole("textbox", { name: "Guided cost (from the AP MIP portal)" }),
      "134367",
    );
    await user.type(
      screen.getByRole("textbox", { name: "Fittings and accessories (from the portal)" }),
      "0",
    );

    expect(
      await screen.findByText("Guided cost (the portal's total)", {}, SETTLE),
    ).toBeInTheDocument();
    const summary = await screen.findByRole("region", { name: "Quotation summary table" });
    await waitFor(() => {
      expect(
        within(summary).getByRole("rowheader", { name: "GST paid by the state" }),
      ).toBeInTheDocument();
    });
  });
});
