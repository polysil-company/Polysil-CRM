import type { PaginationState, RowSelectionState, SortingState } from "@tanstack/react-table";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { DataTable } from "./data-table";
import { createSelectionColumn } from "./selection-column";
import { createDataTableColumnHelper } from "./table-features";

interface Person {
  id: string;
  name: string;
  amount: number;
}

const helper = createDataTableColumnHelper<Person>();

const columns = helper.columns([
  createSelectionColumn(helper, (person) => person.name),
  helper.accessor("name", { header: "Name", meta: { isRowHeader: true } }),
  helper.accessor("amount", { header: "Amount", meta: { align: "end" } }),
]);

const people: Person[] = [
  { id: "p1", name: "Ramesh", amount: 10 },
  { id: "p2", name: "Meena", amount: 20 },
];

interface RenderTableOptions {
  rowCount?: number | null;
  rowCountCapped?: boolean;
  hasNextPage?: boolean;
  isPaging?: boolean;
  pagination?: PaginationState;
  rowSelection?: RowSelectionState;
  sorting?: SortingState;
}

function renderTable(options: RenderTableOptions = {}): {
  onSortingChange: (sorting: SortingState) => void;
  onPaginationChange: (pagination: PaginationState) => void;
  onRowSelectionChange: (selection: RowSelectionState) => void;
} {
  const onSortingChange = vi.fn<(sorting: SortingState) => void>();
  const onPaginationChange = vi.fn<(pagination: PaginationState) => void>();
  const onRowSelectionChange = vi.fn<(selection: RowSelectionState) => void>();

  renderWithProviders(
    <DataTable
      label="People"
      columns={columns}
      data={people}
      getRowId={(person) => person.id}
      rowCount={options.rowCount === undefined ? people.length : options.rowCount}
      {...(options.rowCountCapped === undefined ? {} : { rowCountCapped: options.rowCountCapped })}
      {...(options.hasNextPage === undefined ? {} : { hasNextPage: options.hasNextPage })}
      {...(options.isPaging === undefined ? {} : { isPaging: options.isPaging })}
      sorting={options.sorting ?? []}
      onSortingChange={onSortingChange}
      pagination={options.pagination ?? { pageIndex: 0, pageSize: 25 }}
      onPaginationChange={onPaginationChange}
      rowSelection={options.rowSelection ?? {}}
      onRowSelectionChange={onRowSelectionChange}
    />,
  );

  return { onSortingChange, onPaginationChange, onRowSelectionChange };
}

describe("[DS-001] DataTable", () => {
  it("renders a named table with row headers", () => {
    renderTable();

    expect(screen.getByRole("table", { name: "People" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Ramesh" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Amount/ })).toHaveAttribute(
      "aria-sort",
      "none",
    );
  });

  it("asks the parent to sort (server-side) when a header is clicked", async () => {
    const user = userEvent.setup();
    const { onSortingChange } = renderTable();

    await user.click(screen.getByRole("button", { name: "Name" }));

    expect(onSortingChange).toHaveBeenCalledWith([{ id: "name", desc: false }]);
  });

  it("reflects the current sort direction for assistive tech", () => {
    renderTable({ sorting: [{ id: "amount", desc: true }] });
    expect(screen.getByRole("columnheader", { name: /Amount/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
  });

  it("selects a single row and all rows on the page", async () => {
    const user = userEvent.setup();
    const { onRowSelectionChange } = renderTable();

    await user.click(screen.getByRole("checkbox", { name: "Select Meena" }));
    expect(onRowSelectionChange).toHaveBeenLastCalledWith({ p2: true });

    await user.click(screen.getByRole("checkbox", { name: "Select all rows on this page" }));
    expect(onRowSelectionChange).toHaveBeenLastCalledWith({ p1: true, p2: true });
  });

  it("marks selected rows for assistive tech", () => {
    renderTable({ rowSelection: { p1: true } });

    expect(screen.getByRole("row", { name: /Ramesh/, selected: true })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /Meena/, selected: true })).not.toBeInTheDocument();
  });

  it("shows the range of rows on the page and moves to the next page", async () => {
    const user = userEvent.setup();
    const { onPaginationChange } = renderTable({
      rowCount: 60,
      pagination: { pageIndex: 0, pageSize: 2 },
    });

    expect(screen.getByText("1–2 of 60")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 30")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next page" }));

    expect(onPaginationChange).toHaveBeenCalledWith({ pageIndex: 1, pageSize: 2 });
  });

  it("shows a capped total as a lower bound, with no page count and an unknown row count", () => {
    renderTable({ rowCount: 1000, rowCountCapped: true, hasNextPage: true });

    expect(screen.getByText("1–2 of 1,000+")).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "People" })).toHaveAttribute("aria-rowcount", "-1");
    expect(screen.getByRole("button", { name: "Next page" })).toBeEnabled();
  });

  it("disables both paging buttons while a page change is still loading", () => {
    renderTable({
      rowCount: 60,
      hasNextPage: true,
      isPaging: true,
      pagination: { pageIndex: 1, pageSize: 2 },
    });

    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("lets a cursor-paged API decide whether there is a next page", () => {
    renderTable({ rowCount: null, hasNextPage: false, pagination: { pageIndex: 3, pageSize: 2 } });

    expect(screen.getByText("7–8")).toBeInTheDocument();
    expect(screen.getByText("Page 4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled();
  });
});
