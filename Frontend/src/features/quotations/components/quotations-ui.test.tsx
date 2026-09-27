import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import { formatInr } from "@/lib/format";
import { mockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadQuotations } from "./lead-quotations";
import { QuotationDetail } from "./quotation-detail";
import { QuotationsTable } from "./quotations-table";

function mockQuotation(
  predicate: (quotation: (typeof mockDb.quotations)[number]) => boolean,
): (typeof mockDb.quotations)[number] {
  const quotation = mockDb.quotations.find(predicate);
  if (quotation === undefined) {
    throw new Error("No matching quotation in the mock database");
  }
  return quotation;
}

describe("[QUOT-001] QuotationsTable", () => {
  it("shows a skeleton, then the current quotations with the total", async () => {
    renderWithProviders(<QuotationsTable />);

    expect(screen.getByRole("status", { name: "Loading quotations" })).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Quotations" });
    const current = mockDb.quotations.filter((quotation) => quotation.superseded_by === null);
    expect(within(table).getAllByRole("rowheader")).toHaveLength(Math.min(25, current.length));
    expect(screen.getByText(new RegExp(`of ${String(current.length)}$`))).toBeInTheDocument();
    expect(within(table).getAllByText("Draft").length).toBeGreaterThan(0);
  });

  it("filters by status from the URL, and explains an empty filtered list", async () => {
    renderWithProviders(<QuotationsTable />, { searchParams: "?status=accepted" });

    const table = await screen.findByRole("table", { name: "Quotations" });
    expect(within(table).queryByText("Negotiation")).not.toBeInTheDocument();
    expect(within(table).getAllByText("Accepted").length).toBeGreaterThan(0);
  });

  it("says when nothing matches the filters", async () => {
    server.use(
      http.get(buildApiUrl("/quotations"), () =>
        HttpResponse.json({ data: [], meta: { limit: 25, next_cursor: null, total: 0 } }),
      ),
    );
    renderWithProviders(<QuotationsTable />, { searchParams: "?q=nobody" });

    expect(await screen.findByText("No quotations match these filters")).toBeInTheDocument();
  });

  it("shows older versions when asked, marked as superseded", async () => {
    renderWithProviders(<QuotationsTable />, { searchParams: "?allVersions=true&status=rejected" });

    const table = await screen.findByRole("table", { name: "Quotations" });
    expect(within(table).getAllByText(/Superseded by v2/).length).toBeGreaterThan(0);
  });
});

describe("[QUOT-002] QuotationDetail", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** A stand-in for the tab window.open returns, recording where it was sent. */
  function stubNewTab(): {
    closed: boolean;
    opener: unknown;
    location: { href: string };
    close: () => void;
  } {
    const tab = { closed: false, opener: {}, location: { href: "" }, close: vi.fn() };
    vi.stubGlobal(
      "open",
      vi.fn(() => tab),
    );
    return tab;
  }

  it("prints the document: number, status, items, totals and the party", async () => {
    const wire = mockQuotation(
      (quotation) => quotation.status === "accepted" && quotation.lines.length > 1,
    );
    renderWithProviders(<QuotationDetail quotationId={wire.id} />);

    expect(screen.getByRole("status", { name: "Loading quotation" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: wire.quote_no ?? "" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /Quotation items/ });
    expect(within(table).getAllByRole("row")).toHaveLength(wire.lines.length + 1);
    expect(screen.getByLabelText("Totals")).toHaveTextContent(
      formatInr(wire.totals.total, { paise: true }),
    );
    expect(screen.getByText("Accepted by the customer", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText(wire.party.name).length).toBeGreaterThan(0);
  });

  it("points an older version to the one that replaced it", async () => {
    const older = mockQuotation((quotation) => quotation.superseded_by !== null);
    renderWithProviders(<QuotationDetail quotationId={older.id} />);

    const link = await screen.findByRole("link", { name: "Open version 2" });
    expect(link).toHaveAttribute("href", `/quotations/${older.superseded_by?.id ?? ""}`);
  });

  it("shows the indicative-pricing banner on stand-in prices", async () => {
    const provisional = mockQuotation((quotation) => quotation.is_provisional);
    renderWithProviders(<QuotationDetail quotationId={provisional.id} />);

    expect(await screen.findByText("Indicative pricing")).toBeInTheDocument();
  });

  it("opens the PDF's signed link in a new tab", async () => {
    const user = userEvent.setup();
    const ready = mockQuotation((quotation) => quotation.pdf_state === "ready");
    const tab = stubNewTab();
    renderWithProviders(<QuotationDetail quotationId={ready.id} />);

    await user.click(await screen.findByRole("button", { name: "Open PDF" }));

    expect(window.open).toHaveBeenCalledWith("", "_blank");
    await waitFor(() => {
      expect(tab.location.href).toMatch(/\.pdf$/);
    });
    expect(tab.opener).toBeNull();
  });

  it("says the PDF is still being prepared, and keeps the button off until it is", async () => {
    const pending = mockQuotation((quotation) => quotation.pdf_state === "pending");
    renderWithProviders(<QuotationDetail quotationId={pending.id} />);

    expect(await screen.findByRole("button", { name: /Preparing PDF/ })).toBeDisabled();
    expect(screen.getByText(/checks again by itself/)).toBeInTheDocument();
  });

  it("tells the reader when the PDF link is refused", async () => {
    const user = userEvent.setup();
    const ready = mockQuotation((quotation) => quotation.pdf_state === "ready");
    const tab = stubNewTab();
    server.use(
      http.get(buildApiUrl("/quotations/:quotationId/pdf"), () =>
        HttpResponse.json(
          { error: { code: "pdf_failed", message: "Renderer timed out." } },
          { status: 409 },
        ),
      ),
    );
    renderWithProviders(
      <>
        <QuotationDetail quotationId={ready.id} />
        <Toaster />
      </>,
    );

    await user.click(await screen.findByRole("button", { name: "Open PDF" }));

    expect(await screen.findByText("The PDF couldn't be made")).toBeInTheDocument();
    expect(tab.close).toHaveBeenCalled();
  });
});

describe("[QUOT-001] LeadQuotations", () => {
  it("lists every version of a lead's quotations, the older one marked superseded", async () => {
    const revised = mockQuotation((quotation) => quotation.supersedes !== null);
    renderWithProviders(<LeadQuotations leadId={revised.lead?.id ?? ""} leadStage="negotiation" />);

    const list = await screen.findByRole("list", { name: "Quotations on this lead" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Superseded by v2")).toBeInTheDocument();
  });

  it("says when a lead has no quotations", async () => {
    const lead = mockDb.leads.find(
      (item) => !mockDb.quotations.some((quotation) => quotation.lead?.id === item.id),
    );
    renderWithProviders(
      <LeadQuotations leadId={lead?.id ?? ""} leadStage={lead?.stage ?? "new"} />,
    );

    expect(await screen.findByText("No quotations yet")).toBeInTheDocument();
  });
});
