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

  it("sorts by customer and value on the server, and starts again from the first page (BE-001)", async () => {
    const user = userEvent.setup();
    const sent: URL[] = [];
    // Notes each request and returns nothing, so the mock backend still answers it.
    server.use(
      http.get(buildApiUrl("/leads"), ({ request }) => {
        sent.push(new URL(request.url));
      }),
    );
    const onUrlChange = vi.fn<(queryString: string) => void>();
    renderWithProviders(<LeadsTable />, { onUrlChange });

    const table = await screen.findByRole("table", { name: "Leads" });
    await user.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => {
      expect(screen.getByText(/^26–50 of \d+$/)).toBeInTheDocument();
    });

    const customer = within(table).getByRole("columnheader", { name: /Customer/ });
    expect(customer).toHaveAttribute("aria-sort", "none");
    await user.click(within(customer).getByRole("button", { name: /Customer/ }));

    await waitFor(() => {
      expect(screen.getByText(/^1–25 of \d+$/)).toBeInTheDocument();
    });
    expect(customer).toHaveAttribute("aria-sort", "ascending");
    const last = sent.at(-1);
    expect(last?.searchParams.get("sort")).toBe("farmer_name");
    expect(last?.searchParams.get("order")).toBe("asc");
    // A cursor belongs to one order: the backend refuses it with another sort.
    expect(last?.searchParams.has("cursor")).toBe(false);
    expect(onUrlChange).toHaveBeenLastCalledWith(expect.not.stringContaining("cursors="));

    const names = screen.getAllByRole("rowheader").map((cell) => cell.textContent.toLowerCase());
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, "en-IN")));

    const value = within(table).getByRole("columnheader", { name: /Value/ });
    await user.click(within(value).getByRole("button", { name: /Value/ }));
    await waitFor(() => {
      expect(sent.at(-1)?.searchParams.get("sort")).toBe("estimated_value");
    });
    expect(customer).toHaveAttribute("aria-sort", "none");
  });

  it("names each source from the admin-edited list", async () => {
    renderWithProviders(<LeadsTable />, { searchParams: "?source=agri_fair" });

    const table = await screen.findByRole("table", { name: "Leads" });
    expect(await within(table).findAllByText("Agri Fair")).not.toHaveLength(0);
  });

  it("keeps a source code the administrators wrote with a hyphen", async () => {
    let sent: URL | undefined;
    server.use(
      http.get(buildApiUrl("/leads"), ({ request }) => {
        sent = new URL(request.url);
        return emptyPage(0);
      }),
    );
    renderWithProviders(<LeadsTable />, { searchParams: "?source=agri-fair" });

    // "No leads yet" instead would mean the filter was dropped on the way in.
    expect(await screen.findByText("No leads match these filters")).toBeInTheDocument();
    expect(sent?.searchParams.get("source")).toBe("agri-fair");
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

  it("does not mark a dropdown wrong just because it was opened", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewLeadDialog />, { searchParams: "?newLead=true" });

    const dialog = await screen.findByRole("dialog", { name: "New lead" });
    await user.click(within(dialog).getByRole("combobox", { name: "Inquiry type" }));
    await screen.findByRole("option", { name: "Commercial" });
    await user.keyboard("{Escape}");
    await user.click(within(dialog).getByRole("combobox", { name: "Irrigation system" }));
    await user.keyboard("{Escape}");

    expect(within(dialog).queryByText("Choose the inquiry type.")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Choose the irrigation system.")).not.toBeInTheDocument();
  });

  it("offers a district, taluka or village for the lead, never the state (BE-005)", async () => {
    const searches: URL[] = [];
    server.use(
      // Notes the search, then falls through to the mock backend's own handler.
      http.get(buildApiUrl("/lookups/territories"), ({ request }) => {
        searches.push(new URL(request.url));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<NewLeadDialog />, { searchParams: "?newLead=true" });

    const dialog = await screen.findByRole("dialog", { name: "New lead" });
    await user.type(within(dialog).getByRole("combobox", { name: "Territory" }), "guj");

    // The state is the only place named "Guj…": a lead may not sit in it.
    expect(await screen.findByText("No place matches “guj”.")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Gujarat/ })).not.toBeInTheDocument();
    expect(searches.at(-1)?.searchParams.get("levels")).toBe("district,taluka,village");
  });

  it("sends the crops and land with the lead", async () => {
    let sent: unknown = null;
    server.use(
      // Records the body, then falls through to the mock backend's own handler.
      http.post(buildApiUrl("/leads"), async ({ request }) => {
        sent = await request.clone().json();
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<NewLeadDialog />, { searchParams: "?newLead=true" });

    const dialog = await screen.findByRole("dialog", { name: "New lead" });
    await user.type(within(dialog).getByLabelText("Farmer name"), "Ramesh Patel");
    await user.type(within(dialog).getByLabelText("Mobile number"), "9812345678");
    await user.type(within(dialog).getByRole("combobox", { name: "Territory" }), "gond");
    await user.click(await screen.findByRole("option", { name: /Gondal/ }));
    await user.click(within(dialog).getByRole("combobox", { name: "Inquiry type" }));
    await user.click(await screen.findByRole("option", { name: "Commercial" }));
    await user.click(within(dialog).getByRole("combobox", { name: "Irrigation system" }));
    await user.click(await screen.findByRole("option", { name: "Drip" }));
    await user.click(within(dialog).getByRole("combobox", { name: /Crops/ }));
    await user.click(await screen.findByRole("option", { name: "Cotton" }));
    await user.click(await screen.findByRole("option", { name: "Groundnut" }));
    await user.keyboard("{Escape}");
    expect(within(dialog).getByRole("combobox", { name: /Crops/ })).toHaveTextContent(
      "Cotton, Groundnut",
    );
    await user.type(within(dialog).getByLabelText(/Land/), "4.5");
    await user.click(within(dialog).getByRole("button", { name: "Create lead" }));

    await waitFor(() => {
      expect(sent).toMatchObject({ crops: ["cotton", "groundnut"], land_acres: "4.5" });
    });
  });
});
