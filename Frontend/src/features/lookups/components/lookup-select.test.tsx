import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type * as React from "react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/render";

import { LookupSelect } from "./lookup-select";

const PLACEHOLDER = "Where the enquiry came from";

function Harness({ clearable }: { clearable: boolean }): React.JSX.Element {
  const [value, setValue] = useState<string | null>(null);
  return (
    <>
      <label htmlFor="source">Source</label>
      <LookupSelect
        id="source"
        list="lead-sources"
        clearable={clearable}
        value={value}
        placeholder={PLACEHOLDER}
        onValueChange={setValue}
      />
    </>
  );
}

/** The field is disabled until the administrators' list has arrived. */
async function openTheList(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  const trigger = screen.getByRole("combobox", { name: "Source" });
  await waitFor(() => {
    expect(trigger).toBeEnabled();
  });
  await user.click(trigger);
  return trigger;
}

describe("[MSTR-002] LookupSelect", () => {
  it("offers the list's rows by name and keeps the chosen one", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness clearable />);

    const trigger = await openTheList(user);
    await user.click(await screen.findByRole("option", { name: "Agri Fair" }));

    expect(trigger).toHaveTextContent("Agri Fair");
  });

  it("can be emptied again when the field may be left empty", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness clearable />);

    const trigger = await openTheList(user);
    await user.click(await screen.findByRole("option", { name: "Agri Fair" }));
    await user.click(trigger);
    await user.click(await screen.findByRole("option", { name: "Not set" }));

    expect(trigger).toHaveTextContent(PLACEHOLDER);
  });

  it("offers no way to empty a field that needs a value", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness clearable={false} />);

    await openTheList(user);

    expect(await screen.findByRole("option", { name: "Agri Fair" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Not set" })).not.toBeInTheDocument();
  });
});
