import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { createScheme } from "@/features/subsidy/api/subsidy-schemes.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockStateTerritoryId } from "@/mocks/data/subsidy-schemes";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { SubsidyMasters } from "./subsidy-masters";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <SubsidyMasters />
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

async function dialogClosed(): Promise<void> {
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

async function createUp(): Promise<void> {
  const state = mockStateTerritoryId("UP");
  if (state === null) throw new Error("No Uttar Pradesh in the mock");
  await createScheme({
    body: {
      code: "UPMIS",
      name: "UP Micro Irrigation",
      state_territory_id: state,
      template: "GGRC",
      systems: null,
    },
    idempotencyKey: "ui-up",
  });
}

describe("[SUBS-014] SubsidyMasters · schemes", () => {
  beforeEach(reset);
  afterEach(reset);

  it("opens on GGRC's overview: ready on every system, with its stages", async () => {
    signInAs("admin");
    show();
    expect(
      await screen.findByRole("heading", { name: "Gujarat Green Revolution Company" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    const systems = screen.getByRole("list", { name: "Systems" });
    expect(within(systems).getAllByText("Can calculate")).toHaveLength(3);
    expect(screen.getByRole("list", { name: "Stages" })).toBeInTheDocument();
  });

  it("renames a stage", async () => {
    signInAs("admin");
    const user = show();
    await user.click(await screen.findByRole("button", { name: "Rename Application in process" }));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByLabelText("Name");
    await user.clear(input);
    await user.click(within(dialog).getByRole("button", { name: "Rename" }));
    expect(await within(dialog).findByText("Give the stage a name.")).toBeInTheDocument();
    await user.type(input, "Inward");
    await user.click(within(dialog).getByRole("button", { name: "Rename" }));
    await dialogClosed();
    const stages = screen.getByRole("list", { name: "Stages" });
    expect(await within(stages).findByText(/Inward/)).toBeInTheDocument();
  });

  it("checks a new scheme's fields before sending it", async () => {
    signInAs("admin");
    const user = show();
    await user.click(await screen.findByRole("button", { name: "New scheme" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Set up the scheme" }));
    expect(
      within(dialog).getByText("2 to 20 letters, digits or _, e.g. UPMIS."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Name the scheme.")).toBeInTheDocument();
    expect(within(dialog).getByText("Choose the state it serves.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Code"), "ggrc");
    expect(within(dialog).getByText("Another scheme has that code.")).toBeInTheDocument();
  });

  it("sets up a state's scheme and links what it lacks to the table that fills it", async () => {
    signInAs("admin");
    const user = show();
    await user.click(await screen.findByRole("button", { name: "New scheme" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Code"), "upmis");
    await user.type(within(dialog).getByLabelText("Name"), "UP Micro Irrigation");
    await user.type(within(dialog).getByRole("combobox", { name: "State" }), "Uttar");
    await user.click(await screen.findByRole("option", { name: /Uttar Pradesh/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: "Mini Sprinkler" }));
    await user.click(within(dialog).getByRole("button", { name: "Set up the scheme" }));
    await dialogClosed();

    expect(await screen.findByRole("heading", { name: "UP Micro Irrigation" })).toBeInTheDocument();
    expect(await screen.findByText("Not ready")).toBeInTheDocument();
    const systems = screen.getByRole("list", { name: "Systems" });
    expect(within(systems).getAllByRole("listitem").length).toBeGreaterThanOrEqual(2);
    expect(within(systems).queryByText("Mini Sprinkler")).not.toBeInTheDocument();
    const drip = within(systems).getByRole("list", { name: "What Drip lacks" });
    expect(within(drip).getByText("The regular unit-cost matrix")).toBeInTheDocument();
    await user.click(
      within(drip).getByRole("button", {
        name: "Open the table for the regular unit-cost matrix",
      }),
    );
    expect(screen.getByRole("tab", { name: "Unit costs" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("asks for GGRC to be linked to its state first, then allows a new scheme", async () => {
    const ggrc = mockDb.subsidySchemes[0];
    if (ggrc === undefined) throw new Error("No GGRC");
    ggrc.state_territory_id = null;
    signInAs("admin");
    const user = show();
    expect(
      await screen.findByText("Link GGRC to its state before adding another state's scheme."),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "New scheme" })).toBeDisabled();
    });
    await user.click(screen.getByRole("button", { name: "Link GGRC to a state" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("combobox", { name: "State" }), "Guj");
    await user.click(await screen.findByRole("option", { name: /Gujarat/ }));
    await user.click(within(dialog).getByRole("button", { name: "Link" }));
    await dialogClosed();
    await waitFor(() => {
      expect(
        screen.queryByText("Link GGRC to its state before adding another state's scheme."),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "New scheme" })).toBeEnabled();
  });

  it("switches a scheme off after saying what happens to its applications", async () => {
    signInAs("admin");
    const user = show();
    await user.click(await screen.findByRole("button", { name: "Switch off" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/carry on as they are/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Switch off" }));
    await dialogClosed();
    expect(await screen.findByText("Switched off")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Switch on" })).toBeInTheDocument();
  });

  it("shows no changes to whoever may not edit masters", async () => {
    signInAs("state_manager");
    show();
    expect(
      await screen.findByRole("heading", { name: "Gujarat Green Revolution Company" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New scheme" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Rename/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Switch off" })).not.toBeInTheDocument();
  });
});

describe("[SUBS-012] SubsidyMasters · tables", () => {
  beforeEach(reset);
  afterEach(reset);

  it("adds a new scheme's first rows from a date", async () => {
    await createUp();
    signInAs("admin");
    const user = show("scheme=UPMIS&table=crop-spacings");
    expect(await screen.findByText("Nothing in force on this date")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add rows from a date" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Add a crop" }));
    const row = within(dialog).getByRole("listitem", { name: "New row 1" });
    await user.type(within(row).getByLabelText("Crop"), "Wheat");
    await user.type(within(row).getByLabelText("Standard spacing"), "1.5");
    await user.click(within(dialog).getByRole("button", { name: "Save the revision" }));
    await dialogClosed();
    const table = await screen.findByRole("table", { name: "Crop spacings in force" });
    expect(within(table).getByText("Wheat")).toBeInTheDocument();
  });
});
