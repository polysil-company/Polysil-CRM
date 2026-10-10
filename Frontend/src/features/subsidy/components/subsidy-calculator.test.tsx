import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { SubsidyCalculator } from "./subsidy-calculator";

/** The calculation waits for typing to pause; give it room. */
const SETTLE = { timeout: 3000 };

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(<SubsidyCalculator />);
  return user;
}

async function fillCrop(
  user: ReturnType<typeof userEvent.setup>,
  { area, spacing }: { area: string; spacing: string },
): Promise<void> {
  await user.type(await screen.findByRole("textbox", { name: /^Area/ }), area);
  await user.type(screen.getByRole("textbox", { name: /^Lateral spacing/ }), spacing);
}

describe("[SUBS-002] SubsidyCalculator", () => {
  afterEach(() => {
    writeMockRole("admin");
  });

  it("names the categories first, then shows the figures once area and spacing are in", async () => {
    signInAs("employee");
    const user = show();

    const preview = await screen.findByRole("list", { name: "Farmer categories" });
    expect(within(preview).getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Enter each crop's area and lateral spacing to see the subsidy.",
    );

    await fillCrop(user, { area: "1.5", spacing: "5" });

    const categories = await screen.findByRole("table", { name: /Farmer categories for/ }, SETTLE);
    // Header and all eight, always — a row that doesn't apply is greyed, not dropped.
    expect(within(categories).getAllByRole("row")).toHaveLength(9);
    expect(screen.getByRole("status")).toHaveTextContent(/Figures from the masters in force/);
    const summary = screen.getByRole("table", { name: "Quotation summary" });
    expect(within(summary).getByRole("rowheader", { name: "Total with GST" })).toBeInTheDocument();
    expect(
      within(summary).getByRole("rowheader", { name: "D · Insurance (0.28%)" }),
    ).toBeInTheDocument();
  });

  it("shows the spacing the subsidy uses when the inter-crop's standard is wider", async () => {
    signInAs("employee");
    const user = show();

    await user.type(await screen.findByRole("combobox", { name: /^Inter-crop/ }), "Pome");
    await user.click(await screen.findByRole("option", { name: /Pomegranate/ }));
    await fillCrop(user, { area: "1", spacing: "1.2" });

    expect(
      await screen.findByText(
        /the subsidy runs at 4.50 m. A tighter design earns no more./,
        {},
        SETTLE,
      ),
    ).toBeInTheDocument();
    // Designed 1.20, standard and used 4.50.
    expect(screen.getByText("1.20 m")).toBeInTheDocument();
    expect(screen.getAllByText("4.50 m")).toHaveLength(2);
  });

  it("marks a mistake on its field, and a refusal from the backend too", async () => {
    signInAs("employee");
    const user = show();

    await user.type(await screen.findByRole("textbox", { name: /^Area/ }), "1.2345");
    expect(await screen.findByText("Use at most 3 decimals.", {}, SETTLE)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Area/ })).toHaveAttribute("aria-invalid", "true");

    const area = screen.getByRole("textbox", { name: /^Area/ });
    await user.clear(area);
    await user.type(area, "2");
    await user.type(screen.getByRole("textbox", { name: /^Lateral spacing/ }), "1.2");
    await user.type(screen.getByRole("textbox", { name: /^Group's total area/ }), "1");

    expect(
      await screen.findByText("must be at least the sum of the crop areas", {}, SETTLE),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Group's total area/ })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("takes a second crop block on Drip and prints a column for each", async () => {
    signInAs("employee");
    const user = show();

    await user.click(await screen.findByRole("button", { name: "Add a crop block" }));
    const areas = screen.getAllByRole("textbox", { name: /^Area/ });
    const spacings = screen.getAllByRole("textbox", { name: /^Lateral spacing/ });
    for (const [index, input] of areas.entries()) await user.type(input, index === 0 ? "1" : "0.5");
    for (const input of spacings) await user.type(input, "2");

    const summary = await screen.findByRole("table", { name: "Quotation summary" }, SETTLE);
    expect(within(summary).getByRole("columnheader", { name: "Block 2" })).toBeInTheDocument();
    expect(within(summary).getByRole("columnheader", { name: "Total" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add a crop block" })).not.toBeInTheDocument();
  });

  it("runs Sprinkler from a tabulated area and a nozzle, and lists what it derived", async () => {
    signInAs("employee");
    const user = show();

    await user.click(await screen.findByRole("tab", { name: "Sprinkler" }));
    expect(screen.queryByRole("heading", { name: "Head unit" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: /^Area/ }));
    await user.click(await screen.findByRole("option", { name: "1.200 Ha" }));
    await user.type(screen.getByRole("textbox", { name: /^Lateral spacing/ }), "12");
    await user.click(screen.getByRole("radio", { name: "Brass" }));

    expect(
      await screen.findByText(/75 mm pipe for this area, brass nozzles/, {}, SETTLE),
    ).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Derived items" })).toBeInTheDocument();
    expect(screen.getByText(/Spacing outside the scheme's table/)).toBeInTheDocument();
  });

  it("says a dealer may not see it", async () => {
    signInAs("dealer");
    show();
    expect(await screen.findByText("You don't have access to this")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Drip" })).not.toBeInTheDocument();
  });
});
