import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { mockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadsTable } from "./leads-table";
import { NewLeadDialog } from "./new-lead-dialog";

function emptyPage(total: number | null = 0): Response {
  return HttpResponse.json({ data: [], meta: { limit: 25, next_cursor: null, total } });
}

describe("[LEAD-001] LeadsTable", () => {
  it("shows a skeleton, then the first page of leads with the total", async () => {
    renderWithProviders(<LeadsTable />);

    expect(screen.getByRole("status", { name: "Loading leads" })).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Leads" })).toBeInTheDocument();
    expect(screen.getAllByRole("rowheader")).toHaveLength(25);
    expect(screen.getByText(/^1–25 of \d+$/)).toBeInTheDocument();
  });

  it("names each source from the admin-edited list", async () => {
    renderWithProviders(<LeadsTable />, { searchParams: "?source=agri_fair" });

    const table = await screen.findByRole("table", { name: "Leads" });
    expect(await within(table).findAllByText("Agri Fair")).not.toHaveLength(0);
  });

  it("moves to the next page with the page token, and back", async () => {
    const user = userEvent.setup();
    const onUrlChange = vi.fn<(queryString: string) => void>();
    renderWithProviders(<LeadsTable />, { onUrlChange });

    await screen.findByRole("table", { name: "Leads" });
    const firstName = screen.getAllByRole("rowheader")[0]?.textContent;
    await user.click(screen.getByRole("button", { name: "Next page" }));

    await waitFor(() => {
      expect(screen.getByText(/^26–50 of \d+$/)).toBeInTheDocument();
    });
    expect(onUrlChange).toHaveBeenLastCalledWith(expect.stringContaining("cursors="));
    expect(screen.getAllByRole("rowheader")[0]?.textContent).not.toBe(firstName);

    await user.click(screen.getByRole("button", { name: "Previous page" }));
    await waitFor(() => {
      expect(screen.getByText(/^1–25 of \d+$/)).toBeInTheDocument();
    });
  });

  it("shows a capped total as a lower bound, without a page count", async () => {
    server.use(
      http.get(buildApiUrl("/leads"), () =>
        HttpResponse.json({
          data: mockDb.leads.slice(0, 25).map((lead) => ({ ...lead, duplicates: [] })),
          meta: { limit: 25, next_cursor: "b2Zmc2V0OjI1", total: 1000, total_capped: true },
        }),
      ),
    );
    renderWithProviders(<LeadsTable />);

    expect(await screen.findByText("1–25 of 1,000+")).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Leads" })).toHaveAttribute("aria-rowcount", "-1");
  });

  it("offers the first page when a later page has emptied since the link was made", async () => {
    server.use(http.get(buildApiUrl("/leads"), () => emptyPage(30)));
    renderWithProviders(<LeadsTable />, { searchParams: "?cursors=b2Zmc2V0OjI1" });

    expect(await screen.findByText("This page is empty")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to the first page" })).toBeInTheDocument();
  });

  it("explains an empty result when the filters match nothing", async () => {
    renderWithProviders(<LeadsTable />, { searchParams: "?q=no-such-lead-anywhere" });

    expect(await screen.findByText("No leads match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("shows a first-run empty state when there are no leads at all", async () => {
    server.use(http.get(buildApiUrl("/leads"), () => emptyPage()));
    renderWithProviders(<LeadsTable />);

    expect(await screen.findByText("No leads yet")).toBeInTheDocument();
  });

  it("offers the first page when a page link no longer works", async () => {
    renderWithProviders(<LeadsTable />, { searchParams: "?cursors=not-a-cursor" });

    expect(await screen.findByText("This page link no longer works")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to the first page" })).toBeInTheDocument();
  });

  it("shows a server error with a reference and a retry", async () => {
    server.use(
      http.get(buildApiUrl("/leads"), () =>
        HttpResponse.json({ error: { code: "BOOM", message: "boom" } }, { status: 500 }),
      ),
    );
    renderWithProviders(<LeadsTable />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByText(/^LEAD-001 · /)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("treats a malformed response as a contract violation, without retry", async () => {
    server.use(http.get(buildApiUrl("/leads"), () => HttpResponse.json({ data: "not a list" })));
    renderWithProviders(<LeadsTable />);

    expect(await screen.findByRole("alert")).toHaveTextContent("We received data we couldn't read");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});

describe("[LEAD-002] NewLeadDialog", () => {
  it("opens from its button", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewLeadDialog />);

    await user.click(screen.getByRole("button", { name: "New lead" }));

    expect(await screen.findByRole("dialog", { name: "New lead" })).toBeInTheDocument();
  });

  it("opens from the URL and explains every missing field on submit", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewLeadDialog />, { searchParams: "?newLead=true" });

    const dialog = await screen.findByRole("dialog", { name: "New lead" });
    await user.click(within(dialog).getByRole("button", { name: "Create lead" }));

    expect(await within(dialog).findByText("Enter the farmer's name.")).toBeInTheDocument();
    expect(within(dialog).getByText("Enter a 10-digit Indian mobile number.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose where the farmer is.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose the inquiry type.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose the irrigation system.")).toBeInTheDocument();
  });
});
