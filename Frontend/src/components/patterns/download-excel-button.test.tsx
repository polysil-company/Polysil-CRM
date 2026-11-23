import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { exportPartners } from "@/features/partners/api/partners.api";
import type { DownloadedFile, ExportFormat } from "@/lib/api/client";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { createLogger } from "@/lib/logger";
import { renderWithProviders } from "@/test/render";

import { DownloadExcelButton } from "./download-excel-button";

const saveFile = vi.fn();
vi.mock("@/lib/api/save-file", () => ({
  saveFile: (...args: unknown[]) => {
    saveFile(...args);
  },
}));

const log = createLogger({
  file: "components/patterns/download-excel-button.test.tsx",
  dataId: "APP-011",
});

function file(name: string): DownloadedFile {
  return { blob: new Blob(["x"]), filename: name };
}

describe("[APP-011] DownloadExcelButton (FS-077)", () => {
  it("downloads Excel, and CSV from the other formats", { timeout: 15_000 }, async () => {
    const download = vi.fn((format: ExportFormat) => Promise.resolve(file(`orders.${format}`)));
    const user = userEvent.setup();
    renderWithProviders(
      <DownloadExcelButton
        download={download}
        fallbackName="orders.xlsx"
        what="orders"
        logger={log}
        dataId="APP-011"
      />,
    );

    await user.click(screen.getByRole("button", { name: "Download Excel" }));
    await vi.waitFor(() => {
      expect(download).toHaveBeenLastCalledWith("xlsx");
    });
    // "Downloaded" shows for a moment; the next download waits until the button is idle again.
    await vi.waitFor(
      () => {
        expect(screen.getByRole("button", { name: "Download Excel" })).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    await user.click(await screen.findByRole("button", { name: "Other formats" }));
    await user.click(await screen.findByRole("menuitem", { name: "Download CSV" }));
    await vi.waitFor(() => {
      expect(download).toHaveBeenLastCalledWith("csv");
    });
    await vi.waitFor(() => {
      expect(saveFile).toHaveBeenLastCalledWith(
        expect.objectContaining({ filename: "orders.csv" }),
        "orders.csv",
      );
    });
    expect(screen.queryByRole("menuitem", { name: "Download PDF" })).not.toBeInTheDocument();
  });

  it("offers PDF where the caller says it may", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <DownloadExcelButton
        download={(format) => Promise.resolve(file(`report.${format}`))}
        fallbackName="report.xlsx"
        what="rows"
        logger={log}
        dataId="APP-011"
        otherFormats={["csv", "pdf"]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Other formats" }));
    expect(await screen.findByRole("menuitem", { name: "Download PDF" })).toBeInTheDocument();
  });

  it("asks the backend for CSV, which answers a .csv file", async () => {
    writeMockRole("admin");
    const csv = await exportPartners(
      { q: "", type: null, parentId: null, active: true, cursor: null },
      "csv",
    );
    expect(csv.filename).toMatch(/\.csv$/);
    expect(await csv.blob.text()).toContain(",");
  });
});
