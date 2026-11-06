import { queryOptions, useQuery } from "@tanstack/react-query";
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render";

import { QueryView } from "./query-view";

function Harness({ fetchItems }: { fetchItems: () => Promise<string[]> }): React.JSX.Element {
  const query = useQuery(queryOptions({ queryKey: ["query-view-test"], queryFn: fetchItems }));

  return (
    <QueryView
      query={query}
      pending={<p>Loading items</p>}
      isEmpty={(items) => items.length === 0}
      empty={<p>Nothing here yet</p>}
    >
      {(items) => (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </QueryView>
  );
}

describe("[DS-001] QueryView", () => {
  it("shows pending, then the data", async () => {
    renderWithProviders(<Harness fetchItems={() => Promise.resolve(["Cotton", "Banana"])} />);

    expect(screen.getByText("Loading items")).toBeInTheDocument();
    expect(await screen.findByText("Cotton")).toBeInTheDocument();
  });

  it("shows the empty state for empty data", async () => {
    renderWithProviders(<Harness fetchItems={() => Promise.resolve([])} />);

    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
  });

  it("shows an error with a working retry", async () => {
    const user = userEvent.setup();
    const fetchItems = vi
      .fn<() => Promise<string[]>>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(["Wheat"]);
    renderWithProviders(<Harness fetchItems={fetchItems} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Wheat")).toBeInTheDocument();
  });

  it("keeps showing data when a refresh fails, with a retry notice", async () => {
    const fetchItems = vi
      .fn<() => Promise<string[]>>()
      .mockResolvedValueOnce(["Onion"])
      .mockRejectedValue(new Error("offline"));
    const { queryClient } = renderWithProviders(<Harness fetchItems={fetchItems} />);
    expect(await screen.findByText("Onion")).toBeInTheDocument();

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["query-view-test"] });
    });

    expect(
      await screen.findByText("Couldn't refresh. Showing the last loaded data."),
    ).toBeInTheDocument();
    expect(screen.getByText("Onion")).toBeInTheDocument();
  });
});
