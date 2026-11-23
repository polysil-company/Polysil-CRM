import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { ProductPick } from "@/features/quotations/api/quotations.schemas";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";
import { renderWithProviders } from "@/test/render";

import { ProductPicker } from "./product-picker";

const LONG_NAME = "EMITTING PIPE 16 MM 40 CM SPACING 2 LPH";

function Harness(): React.JSX.Element {
  const [value, setValue] = useState<ProductPick | null>(null);
  return (
    <ProductPicker
      id="item-1-product"
      aria-label="Product"
      value={value}
      onValueChange={setValue}
    />
  );
}

describe("[MSTR-003] ProductPicker with long product names", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
  });

  it("shows a chosen product's full name under the field, which can only cut it off", async () => {
    writeMockRole("admin");
    const user = userEvent.setup();
    renderWithProviders(<Harness />);
    const input = screen.getByRole("combobox", { name: "Product" });
    expect(input).not.toHaveAttribute("title");

    await user.type(input, "EMITTING");
    await user.click(await screen.findByRole("option", { name: new RegExp(`^${LONG_NAME}`) }));

    await waitFor(() => {
      expect(input).toHaveValue(LONG_NAME);
    });
    expect(input).toHaveAttribute("title", LONG_NAME);
    expect(screen.getByText(LONG_NAME, { selector: "p" })).toBeInTheDocument();
  });
});
