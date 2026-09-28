import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import { getQuotation, getQuotationPdf, listQuotations } from "./quotations.api";
import type { QuotationListParams } from "./quotations.schemas";

const FIRST_PAGE: QuotationListParams = {
  cursor: null,
  pageSize: 25,
  q: "",
  status: [],
  salesType: null,
  currentOnly: true,
  leadId: null,
};

function mockQuotation(
  predicate: (quotation: (typeof mockDb.quotations)[number]) => boolean,
): (typeof mockDb.quotations)[number] {
  const quotation = mockDb.quotations.find(predicate);
  if (quotation === undefined) {
    throw new Error("No matching quotation in the mock database");
  }
  return quotation;
}

describe("[QUOT-001] listQuotations", () => {
  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("returns the current versions, newest first, with the total", async () => {
    const page = await listQuotations(FIRST_PAGE);

    const current = mockDb.quotations.filter((quotation) => quotation.superseded_by === null);
    expect(page.total).toBe(current.length);
    expect(page.items.every((quotation) => quotation.supersededBy === null)).toBe(true);
    const times = page.items.map((quotation) => Date.parse(quotation.createdAt));
    expect([...times].sort((a, b) => b - a)).toEqual(times);
  });

  it("sends several statuses as one comma-separated value, and current_only only when off", async () => {
    let sent: URL | undefined;
    server.events.on("request:start", ({ request }) => {
      sent = new URL(request.url);
    });

    await listQuotations({ ...FIRST_PAGE, status: ["sent", "viewed"] });
    expect(sent?.searchParams.get("status")).toBe("sent,viewed");
    expect(sent?.searchParams.has("current_only")).toBe(false);

    await listQuotations({ ...FIRST_PAGE, currentOnly: false });
    expect(sent?.searchParams.get("current_only")).toBe("false");
  });

  it("shows every version of a lead's quotations when asked", async () => {
    const revised = mockQuotation((quotation) => quotation.supersedes !== null);
    const leadId = revised.lead?.id ?? null;

    const page = await listQuotations({ ...FIRST_PAGE, leadId, currentOnly: false });

    expect(page.items.map((quotation) => quotation.version).sort()).toEqual([1, 2]);
  });

  it("finds a quotation by its number", async () => {
    const sent = mockQuotation((quotation) => quotation.quote_no !== null);

    const page = await listQuotations({ ...FIRST_PAGE, q: sent.quote_no ?? "" });

    expect(page.items.map((quotation) => quotation.quoteNo)).toContain(sent.quote_no);
  });
});

describe("[QUOT-002] getQuotation", () => {
  it("reads the document with its lines and every tier of the discount", async () => {
    const wire = mockQuotation((quotation) => quotation.lines.length > 0);

    const quotation = await getQuotation(wire.id);

    expect(quotation.lines).toHaveLength(wire.lines.length);
    expect(quotation.lines[0]?.discounts).toHaveLength(3);
    expect(quotation.totals.total).toBe(wire.totals.total);
    expect(quotation.seller.gstin).toBe(wire.seller_gstin.gstin);
  });

  it("reads a quotation whose lead is out of sight, with no owner", async () => {
    const wire = mockQuotation((quotation) => quotation.lines.length > 0);
    server.use(
      http.get(buildApiUrl("/quotations/:quotationId"), () =>
        HttpResponse.json({ data: { ...wire, lead: null, owner: null } }),
      ),
    );

    const quotation = await getQuotation(wire.id);

    expect(quotation.lead).toBeNull();
    expect(quotation.owner).toBeNull();
  });

  it("reports a quotation outside the caller's scope as 404", async () => {
    await expect(getQuotation("missing")).rejects.toMatchObject({
      status: 404,
      dataId: "QUOT-002",
    });
  });
});

describe("[QUOT-002] names the backend may leave blank", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("reads a quotation whose office, territory, price list or seller name is blank", async () => {
    const wire = mockQuotation((quotation) => quotation.price_list !== null);
    wire.owner_org_unit = { ...wire.owner_org_unit, name: "" };
    wire.territory = { ...wire.territory, name: " ", level: "" };
    wire.price_list = wire.price_list === null ? null : { ...wire.price_list, name: "" };
    wire.seller_gstin = { ...wire.seller_gstin, legal_name: "" };

    const quotation = await getQuotation(wire.id);

    expect(quotation.ownerOrgUnit.name).toBe("—");
    expect(quotation.territory).toMatchObject({ name: "—", level: "—" });
    expect(quotation.priceList?.name).toBe("—");
    expect(quotation.seller.legalName).toBe("—");
  });
});

describe("[QUOT-003] getQuotationPdf", () => {
  it("returns a signed link for a sent quotation whose PDF is ready", async () => {
    const ready = mockQuotation((quotation) => quotation.pdf_state === "ready");

    const link = await getQuotationPdf(ready.id);

    expect(link.url).toMatch(/^https:\/\//);
    expect(link.filename).toMatch(/\.pdf$/);
  });

  it("refuses a draft with 404 and a PDF still being made with 409 pdf_pending", async () => {
    const draft = mockQuotation((quotation) => quotation.status === "draft");
    await expect(getQuotationPdf(draft.id)).rejects.toMatchObject({ status: 404 });

    const ready = mockQuotation((quotation) => quotation.pdf_state === "ready");
    server.use(
      http.get(buildApiUrl("/quotations/:quotationId/pdf"), () =>
        HttpResponse.json(
          { error: { code: "pdf_pending", message: "Preparing" } },
          { status: 409 },
        ),
      ),
    );
    await expect(getQuotationPdf(ready.id)).rejects.toMatchObject({
      status: 409,
      code: "pdf_pending",
    });
  });
});
