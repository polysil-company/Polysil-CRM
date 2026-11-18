import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";
import { renderWithProviders } from "@/test/render";

import { StockLedger } from "./stock-ledger";
import { StockList } from "./stock-list";

const saveFile = vi.fn();
vi.mock("@/lib/api/save-file", () => ({
  saveFile: (...args: unknown[]) => {
    saveFile(...args);
  },
}));

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  saveFile.mockClear();
}

describe("[APP-012] Downloads on the stock screens (FS-081)", () => {
  afterEach(reset);

  it("downloads the stock list as Excel, beside its filters", { timeout: 15_000 }, async () => {
    writeMockRole("admin");
    const user = userEvent.setup();
    renderWithProviders(<StockList />);

    await user.click(await screen.findByRole("button", { name: "Download Excel" }));
    await vi.waitFor(() => {
      expect(saveFile).toHaveBeenCalledWith(
        expect.objectContaining({ filename: expect.stringMatching(/^stock-[\d-]+\.xlsx$/) }),
        "stock.xlsx",
      );
    });
  });

  it("downloads the stock ledger as CSV from the other formats", { timeout: 15_000 }, async () => {
    writeMockRole("admin");
    const user = userEvent.setup();
    renderWithProviders(<StockLedger />);

    await user.click(await screen.findByRole("button", { name: "Other formats" }));
    await user.click(await screen.findByRole("menuitem", { name: "Download CSV" }));
    await vi.waitFor(() => {
      expect(saveFile).toHaveBeenCalledWith(
        expect.objectContaining({
          filename: expect.stringMatching(/^stock-movements-[\d-]+\.csv$/),
        }),
        "stock-movements.csv",
      );
    });
  });
});
