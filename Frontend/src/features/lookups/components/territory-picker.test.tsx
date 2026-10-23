import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { renderWithProviders } from "@/test/render";

import { TerritoryPicker } from "./territory-picker";

function Harness({
  onChange,
}: {
  onChange: (value: TerritoryChoice | null) => void;
}): React.JSX.Element {
  const [value, setValue] = useState<TerritoryChoice | null>(null);
  return (
    <>
      <label htmlFor="territory">Territory</label>
      <TerritoryPicker
        id="territory"
        value={value}
        onValueChange={(next) => {
          setValue(next);
          onChange(next);
        }}
      />
    </>
  );
}

describe("[MSTR-002] TerritoryPicker", () => {
  it("lists districts to start from when opened", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness onChange={vi.fn()} />);

    await user.click(screen.getByRole("combobox", { name: "Territory" }));

    expect(await screen.findByRole("option", { name: /Ahmedabad/ })).toBeInTheDocument();
    expect(screen.getByText("Districts. Type to find a taluka or village.")).toBeInTheDocument();
  });

  it("searches as you type and keeps the chosen place in the field", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn<(value: TerritoryChoice | null) => void>();
    renderWithProviders(<Harness onChange={onChange} />);

    const input = screen.getByRole("combobox", { name: "Territory" });
    await user.type(input, "gond");
    const option = await screen.findByRole("option", { name: /Gondal.*Taluka in Rajkot/ });
    await user.click(option);

    await waitFor(() => {
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ name: "Gondal", level: "taluka" }),
      );
    });
    expect(input).toHaveValue("Gondal");
  });

  it("says when nothing matches", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness onChange={vi.fn()} />);

    await user.type(screen.getByRole("combobox", { name: "Territory" }), "zzzz");

    expect(await screen.findByText("No place matches “zzzz”.")).toBeInTheDocument();
  });
});
