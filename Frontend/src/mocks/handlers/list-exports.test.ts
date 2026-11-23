import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { exportCampaigns } from "@/features/campaigns/api/campaigns.api";
import { exportCustomers } from "@/features/customers/api/customers.api";
import { exportDealerApplications } from "@/features/dealer-applications/api/dealer-applications.api";
import { exportHolidays } from "@/features/masters/api/holidays.api";
import { exportOffices, exportTerritories } from "@/features/masters/api/masters.api";
import { exportPayments } from "@/features/payments/api/payments.api";
import {
  exportPriceListItems,
  exportPriceLists,
  exportProducts,
  exportTaxRates,
} from "@/features/products/api/products.api";
import { exportSellerGstins } from "@/features/products/api/seller-gstins.api";
import { exportRatings } from "@/features/ratings/api/ratings.api";
import {
  exportGifts,
  exportLedger,
  exportRedemptions,
  exportRules,
} from "@/features/rewards/api/rewards.api";
import { exportEntitlements, exportSchemes } from "@/features/schemes/api/schemes.api";
import { exportMovements, exportStock, exportWarehouses } from "@/features/stock/api/stock.api";
import { exportSchemes as exportSubsidySchemes } from "@/features/subsidy/api/subsidy-schemes.api";
import { exportWarrantyTerms } from "@/features/warranty/api/warranty.api";
import type { DownloadedFile, ExportFormat } from "@/lib/api/client";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

type Download = (format: ExportFormat) => Promise<DownloadedFile>;

/** Each list's download, with the file stem and first heading the backend gives it. */
const DOWNLOADS: readonly (readonly [string, string, Download])[] = [
  [
    "products",
    "Item code",
    (format) =>
      exportProducts({ q: "", category: null, quotationCategory: null, active: null }, format),
  ],
  ["tax-rates", "HSN", (format) => exportTaxRates({ hsnCode: null, inForce: true }, format)],
  ["price-lists", "Name", (format) => exportPriceLists({ status: null, salesType: null }, format)],
  [
    "price-list-items",
    "Product",
    (format) => exportPriceListItems({ listId: "pl-1", q: "", unpriced: false }, format),
  ],
  ["seller-gstins", "GSTIN", (format) => exportSellerGstins(format)],
  ["customers", "Name", (format) => exportCustomers({ q: "", territoryId: null }, format)],
  ["warehouses", "Code", (format) => exportWarehouses(true, format)],
  [
    "stock",
    "Warehouse",
    (format) => exportStock({ warehouseId: null, productId: null, shortOnly: false }, format),
  ],
  [
    "stock-movements",
    "When",
    (format) => exportMovements({ warehouseId: null, productId: null }, format),
  ],
  [
    "payments",
    "Received on",
    (format) => exportPayments({ partnerId: null, orderId: null, includeVoided: false }, format),
  ],
  ["warranty-terms", "Product category", (format) => exportWarrantyTerms(format)],
  ["offices", "Name", (format) => exportOffices({ q: "", state: "all" }, format)],
  [
    "territories",
    "Name",
    (format) => exportTerritories({ level: null, parentId: null, q: "" }, format),
  ],
  ["holidays", "Date", (format) => exportHolidays(2026, format)],
  [
    "dealer-applications",
    "Firm",
    (format) => exportDealerApplications({ status: [], q: "", partnerType: null }, format),
  ],
  ["campaigns", "Name", (format) => exportCampaigns({ active: null, type: null, q: "" }, format)],
  ["schemes", "Code", (format) => exportSchemes({ status: null, type: null, q: "" }, format)],
  [
    "scheme-entitlements",
    "Scheme",
    (format) => exportEntitlements({ status: null, partnerId: null }, format),
  ],
  ["subsidy-schemes", "Code", (format) => exportSubsidySchemes(format)],
  [
    "ratings",
    "When",
    (format) =>
      exportRatings(
        { target: null, salesOrderId: null, complaintId: null, partnerId: null, maxScore: null },
        format,
      ),
  ],
  ["reward-points", "When", (format) => exportLedger({ kind: "me" }, format)],
  ["gifts", "Name", (format) => exportGifts(false, format)],
  [
    "gift-redemptions",
    "Requested",
    (format) => exportRedemptions({ status: null, kind: "gift" }, format),
  ],
  ["reward-rules", "Code", (format) => exportRules(format)],
];

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[APP-012] Downloads on 24 more lists (FS-081)", () => {
  afterEach(reset);

  it("covers every list the backend added an export to", () => {
    expect(DOWNLOADS).toHaveLength(24);
  });

  it.each(DOWNLOADS)("downloads %s as Excel and as CSV", async (stem, heading, download) => {
    writeMockRole("admin");
    const excel = await download("xlsx");
    expect(excel.filename).toMatch(new RegExp(`^${stem}-\\d{4}-\\d{2}-\\d{2}\\.xlsx$`));

    const csv = await download("csv");
    expect(csv.filename).toMatch(new RegExp(`^${stem}-\\d{4}-\\d{2}-\\d{2}\\.csv$`));
    expect((await csv.blob.text()).split("\n")[0]?.split(",")[0]).toBe(heading);
  });

  it("sends the list's own filters, and no page or cursor", async () => {
    writeMockRole("admin");
    let asked: URLSearchParams | null = null;
    server.use(
      http.get(buildApiUrl("/stock/export"), ({ request }) => {
        asked = new URL(request.url).searchParams;
        return new HttpResponse("x", {
          headers: { "content-disposition": 'attachment; filename="stock-2026-11-05.csv"' },
        });
      }),
    );

    await exportStock({ warehouseId: "wh-1", productId: "p-9", shortOnly: true }, "csv");

    expect(asked).not.toBeNull();
    expect(Object.fromEntries(asked ?? new URLSearchParams())).toEqual({
      warehouse_id: "wh-1",
      product_id: "p-9",
      short_only: "true",
      format: "csv",
    });
  });

  it("sends the dealer or distributor filter on the applications download (CHNL-007)", async () => {
    writeMockRole("admin");
    let asked: URLSearchParams | null = null;
    server.use(
      http.get(buildApiUrl("/dealer-applications/export"), ({ request }) => {
        asked = new URL(request.url).searchParams;
        return new HttpResponse("x", {
          headers: {
            "content-disposition": 'attachment; filename="dealer-applications-2026-11-06.xlsx"',
          },
        });
      }),
    );

    await exportDealerApplications(
      { status: ["submitted"], q: " Kisan ", partnerType: "distributor" },
      "xlsx",
    );

    expect(Object.fromEntries(asked ?? new URLSearchParams())).toEqual({
      status: "submitted",
      q: "Kisan",
      partner_type: "distributor",
      format: "xlsx",
    });
  });

  it("says when the rows are too many to download", async () => {
    writeMockRole("admin");
    server.use(
      http.get(buildApiUrl("/payments/export"), () =>
        HttpResponse.json(
          { error: { code: "export_too_large", message: "More than 5,000 rows." } },
          { status: 422 },
        ),
      ),
    );

    await expect(
      exportPayments({ partnerId: null, orderId: null, includeVoided: false }),
    ).rejects.toMatchObject({ status: 422, code: "export_too_large" });
  });
});
