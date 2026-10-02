import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { FilterPill, SingleFilterPill } from "./filter-pill";

const TYPES = [
  { value: "commercial", label: "Commercial" },
  { value: "subsidised", label: "Subsidised" },
] as const;

describe("[LEAD-001] SingleFilterPill", () => {
  it("offers the options as radios and reports the one chosen", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(next: string | null) => void>();
    renderWithProviders(
      <SingleFilterPill label="Type" options={TYPES} selected={null} onChange={onChange} />,
    );

    await user.click(screen.getByRole("button", { name: "Type" }));
    await user.click(await screen.findByRole("radio", { name: "Subsidised" }));

    expect(onChange).toHaveBeenLastCalledWith("subsidised");
  });

  it("names the chosen option on the pill and clears it", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(next: string | null) => void>();
    renderWithProviders(
      <SingleFilterPill label="Type" options={TYPES} selected="commercial" onChange={onChange} />,
    );

    const pill = screen.getByRole("button", { name: /Type/ });
    expect(pill).toHaveTextContent("Commercial");
    await user.click(pill);
    await user.click(await screen.findByRole("button", { name: "Clear type" }));

    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("explains why there are no options yet", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SingleFilterPill
        label="Source"
        options={[]}
        selected={null}
        onChange={vi.fn()}
        emptyMessage="Loading sources…"
      />,
    );

    await user.click(screen.getByRole("button", { name: "Source" }));

    expect(await screen.findByText("Loading sources…")).toBeInTheDocument();
  });
});

describe("[LEAD-001] FilterPill with descriptions", () => {
  it("names each option by its label and describes it by the line under it", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <FilterPill
        label="Stage"
        options={[
          { value: "new", label: "New", description: "Just came in." },
          {
            value: "merged",
            label: "Merged",
            description: "A duplicate, folded into another lead.",
          },
        ]}
        selected={[]}
        onChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Stage" }));
    const merged = await screen.findByRole("checkbox", { name: "Merged" });

    expect(merged).toHaveAccessibleDescription("A duplicate, folded into another lead.");
    expect(screen.getByText("Just came in.")).toBeVisible();
  });
});
