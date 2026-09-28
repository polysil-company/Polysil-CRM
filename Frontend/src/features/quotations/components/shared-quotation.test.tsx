import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { getPublicQuotation } from "@/features/quotations/api/quotations.api";
import type { PublicQuotationWire } from "@/features/quotations/api/quotations.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { formatInr } from "@/lib/format";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { SharedQuotation } from "./shared-quotation";

/** The token of a current, sent quotation whose PDF is ready. */
function sharedToken(): { token: string; quoteNo: string; total: string } {
  const quotation = mockDb.quotations.find(
    (item) => item.share_url !== null && item.superseded_by === null && item.pdf_state === "ready",
  );
  const token = quotation?.share_url?.split("/q/")[1];
  if (quotation === undefined || token === undefined) {
    throw new Error("No shared quotation in the mock database");
  }
  return { token, quoteNo: quotation.quote_no ?? "", total: quotation.totals.total };
}

function serve(patch: Partial<PublicQuotationWire["data"]>): void {
  server.use(
    http.get(buildApiUrl("/public/q/:token"), ({ params }) => {
      const body: PublicQuotationWire = {
        data: {
          quote_no: "QT/GJ/2026-27/00042",
          version: 1,
          status: "sent",
          sales_type: "commercial",
          seller: { legal_name: "Polysil Irrigation Systems Pvt Ltd", gstin: "24AAACP1234A1Z5" },
          sent_at: "2026-09-20T10:00:00+05:30",
          valid_until: "2026-11-04",
          expired: false,
          superseded: false,
          totals: {
            gross: "1000.00",
            discount: "0.00",
            taxable: "1000.00",
            cgst: "90.00",
            sgst: "90.00",
            igst: "0.00",
            total: "1180.00",
          },
          line_count: 2,
          pdf_ready: true,
          pdf_url: `/public/q/${String(params.token)}/pdf`,
          ...patch,
        },
      };
      return HttpResponse.json(body);
    }),
  );
}

describe("[QUOT-012] getPublicQuotation", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("reads a shared quotation without signing in, and nothing personal", async () => {
    const shared = sharedToken();
    let authorization: string | null = "unset";
    server.events.on("request:start", ({ request }) => {
      authorization = request.headers.get("authorization");
    });

    const quotation = await getPublicQuotation(shared.token);

    server.events.removeAllListeners();
    expect(authorization).toBeNull();
    expect(quotation).toMatchObject({ quoteNo: shared.quoteNo, pdfReady: true });
    expect(quotation.pdfPath).toBe(`/public/q/${shared.token}/pdf`);
    expect(Object.keys(quotation)).not.toContain("party");
  });

  it("reports an unknown link as 404", async () => {
    await expect(getPublicQuotation("no-such-link")).rejects.toMatchObject({ status: 404 });
  });
});

describe("[QUOT-012] SharedQuotation", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("shows the number, the seller, the total and a link to the PDF", async () => {
    const shared = sharedToken();
    renderWithProviders(<SharedQuotation token={shared.token} />);

    expect(
      await screen.findByRole("heading", { level: 1, name: new RegExp(`^${shared.quoteNo}`) }),
    ).toBeInTheDocument();
    expect(screen.getByText(formatInr(shared.total, { paise: true }))).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "View quotation" });
    expect(link).toHaveAttribute("href", buildApiUrl(`/public/q/${shared.token}/pdf`));
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("says the PDF is being prepared, with no link to open yet", async () => {
    serve({ pdf_ready: false });
    renderWithProviders(<SharedQuotation token="pending-link" />);

    expect(await screen.findByText("Preparing the PDF…")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View quotation" })).not.toBeInTheDocument();
  });

  it("still opens an expired or replaced quotation, saying so", async () => {
    serve({ expired: true, superseded: true, status: "expired", version: 2 });
    renderWithProviders(<SharedQuotation token="old-link" />);

    expect(
      await screen.findByRole("heading", { level: 1, name: /00042\s*·\s*v2$/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/A newer version of this quotation was sent/)).toBeInTheDocument();
    expect(screen.getByText(/This quotation expired on/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View quotation" })).toBeInTheDocument();
  });

  it("explains a link that doesn't open anything", async () => {
    renderWithProviders(<SharedQuotation token="no-such-link" />);

    expect(await screen.findByText("This link doesn't open a quotation")).toBeInTheDocument();
  });
});
