import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { renderWithProviders } from "@/test/render";

import { AreaBySystemCard, TargetsCard } from "./dashboard-charts";
import { DashboardOverview } from "./dashboard-overview";

function rowsOf(list: HTMLElement): string[] {
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.textContent);
}

describe("[RPT-001] AreaBySystemCard", () => {
  it("lists each system's land and leads, most land first", () => {
    render(
      <AreaBySystemCard
        systems={[
          { system: "drip", name: "Drip", leads: 14, hectares: "38.50" },
          { system: "sprinkler", name: "Sprinkler", leads: 1, hectares: "52.00" },
          { system: "automation", name: "Automation", leads: 2, hectares: "0.00" },
        ]}
      />,
    );

    expect(rowsOf(screen.getByRole("list"))).toEqual([
      "Sprinkler52.0 hectares1 lead",
      "Drip38.5 hectares14 leads",
      "Automation0.0 hectares2 leads",
    ]);
    expect(screen.queryByText(/land recorded/)).not.toBeInTheDocument();
  });

  it("says when there is nothing to show, and when no lead has its land recorded", () => {
    const { rerender } = render(<AreaBySystemCard systems={[]} />);
    expect(screen.getByText("No open or won leads yet.")).toBeInTheDocument();

    rerender(
      <AreaBySystemCard systems={[{ system: "drip", name: "Drip", leads: 3, hectares: "0.00" }]} />,
    );
    expect(screen.getByText("None of these leads has its land recorded yet.")).toBeInTheDocument();
  });
});

describe("[RPT-001] TargetsCard", () => {
  it("shows each month's sales against the target, with the share and a key", () => {
    render(
      <TargetsCard
        months={[
          { month: "2026-09", target: "1200000.00", achieved: "984000.00" },
          { month: "2026-10", target: "1200000.00", achieved: "300000.00" },
        ]}
      />,
    );

    expect(
      screen.getByText("Order value sold each month, against your team's target"),
    ).toBeInTheDocument();
    const [months, key] = screen.getAllByRole("list").reverse();
    if (months === undefined || key === undefined) throw new Error("Lists missing");
    expect(rowsOf(months)).toEqual([
      "Sept 2026₹9.84 L of ₹12 L82%",
      "Oct 2026so far₹3 L of ₹12 L25%",
    ]);
    expect(screen.getByRole("list", { name: "Key" })).toHaveTextContent("SoldTarget");
  });

  it("shows targets alone to a role that can't see sales", () => {
    render(
      <TargetsCard
        months={[
          { month: "2026-09", target: "1200000.00", achieved: null },
          { month: "2026-10", target: "0.00", achieved: null },
        ]}
      />,
    );

    expect(screen.getByText("Your team's order value target each month")).toBeInTheDocument();
    expect(screen.getByText("Target ₹12 L")).toBeInTheDocument();
    expect(screen.getByText("No target")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Key" })).toHaveTextContent(/^Target$/);
  });

  it("says when no targets are set, keeping what was sold", () => {
    const { rerender } = render(
      <TargetsCard months={[{ month: "2026-10", target: "0.00", achieved: "0.00" }]} />,
    );
    expect(
      screen.getByText("No targets set and nothing sold in the last six months."),
    ).toBeInTheDocument();

    rerender(<TargetsCard months={[{ month: "2026-10", target: "0.00", achieved: "50000.00" }]} />);
    expect(screen.getByText("no target")).toBeInTheDocument();
    expect(screen.getByText("No targets set for these months.")).toBeInTheDocument();
  });
});

describe("[RPT-001] DashboardOverview charts", () => {
  afterEach(() => {
    writeMockRole("state_manager");
  });

  it("shows both charts to a manager", async () => {
    renderWithProviders(<DashboardOverview />);

    expect(
      await screen.findByRole("heading", { name: "Area by irrigation system" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Orders against target" })).toBeInTheDocument();
  });

  it("leaves the targets chart out for a role without targets", async () => {
    writeMockRole("account_manager");
    renderWithProviders(<DashboardOverview />);

    expect(
      await screen.findByRole("heading", { name: "Area by irrigation system" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Orders against target" }),
    ).not.toBeInTheDocument();
  });
});
