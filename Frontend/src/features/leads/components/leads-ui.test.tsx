import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { LeadsTable } from "./leads-table";
import { NewLeadDialog } from "./new-lead-dialog";

describe("[LEAD-001] LeadsTable", () => {
  it("shows a skeleton, then the first page of leads", async () => {
    renderWithProviders(<LeadsTable />);

    expect(screen.getByRole("status", { name: "Loading leads" })).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Leads" })).toBeInTheDocument();
    expect(screen.getAllByRole("rowheader")).toHaveLength(25);
  });

  it("explains an empty result when the filters match nothing", async () => {
    renderWithProviders(<LeadsTable />, { searchParams: "?q=no-such-lead-anywhere" });

    expect(await screen.findByText("No leads match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("shows a first-run empty state when there are no leads at all", async () => {
    server.use(
      http.get(buildApiUrl("/leads"), () =>
        HttpResponse.json({ items: [], page: 1, pageSize: 25, total: 0 }),
      ),
    );
    renderWithProviders(<LeadsTable />);

    expect(await screen.findByText("No leads yet")).toBeInTheDocument();
  });

  it("offers the first page when the requested page is past the end", async () => {
    server.use(
      http.get(buildApiUrl("/leads"), () =>
        HttpResponse.json({ items: [], page: 9, pageSize: 25, total: 30 }),
      ),
    );
    renderWithProviders(<LeadsTable />, { searchParams: "?page=9" });

    expect(await screen.findByText("This page is empty")).toBeInTheDocument();
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
    server.use(http.get(buildApiUrl("/leads"), () => HttpResponse.json({ items: "not a list" })));
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

    expect(await within(dialog).findByText("Enter the customer's full name.")).toBeInTheDocument();
    expect(within(dialog).getByText("Enter a 10-digit Indian mobile number.")).toBeInTheDocument();
    expect(within(dialog).getByText("Enter the district.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose where this lead came from.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose the order type.")).toBeInTheDocument();
  });
});
