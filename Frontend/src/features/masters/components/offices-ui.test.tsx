import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { Masters } from "./masters";
import { officeProblems, patchRequestOfOffice, emptyOfficeDraft } from "./office-dialog";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(ui: React.JSX.Element): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
    { searchParams: "?tab=offices" },
  );
  return user;
}

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
}

describe("[MSTR-011] Offices", () => {
  afterEach(reset);

  it("lists the open offices with their place, territory, level and people", async () => {
    signInAs("admin");
    show(<Masters />);

    const list = await screen.findByRole("list", { name: "Offices" });
    const rajkot = within(list)
      .getAllByRole("listitem")
      .find((row) => within(row).queryByText("Rajkot District") !== null);
    if (rajkot === undefined) throw new Error("No Rajkot row");
    expect(rajkot).toHaveTextContent("Under Gujarat State · Rajkot · District Manager");
    expect(rajkot).toHaveTextContent("2 people");
    expect(within(list).queryByText("Bhavnagar District (closed)")).not.toBeInTheDocument();
  });

  it("says why an office people work from can't be closed", async () => {
    signInAs("admin");
    const user = show(<Masters />);
    await user.click(await screen.findByRole("button", { name: "Close Rajkot District" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "2 people still work from Rajkot District. Move them to another office, or deactivate them in Users & roles, then close it.",
    );
  });

  it("reopens a closed office from All", async () => {
    signInAs("admin");
    const user = show(<Masters />);
    await screen.findByRole("list", { name: "Offices" });
    await user.click(screen.getByRole("button", { name: "All" }));
    await user.click(
      await screen.findByRole("button", { name: "Reopen Bhavnagar District (closed)" }),
    );

    expect(await screen.findByText("Bhavnagar District (closed) reopened")).toBeInTheDocument();
    expect(
      mockDb.offices.find((office) => office.name === "Bhavnagar District (closed)")?.is_open,
    ).toBe(true);
  });

  it("adds an HQ unit at the top level, naming what is missing first", async () => {
    signInAs("admin");
    const user = show(<Masters />);
    await user.click(await screen.findByRole("button", { name: "New office" }));
    const form = await screen.findByRole("form", { name: "New office" });

    await user.click(within(form).getByRole("button", { name: "Add the office" }));
    expect(within(form).getByText("Enter the office's name.")).toBeInTheDocument();
    expect(within(form).getByText("Choose the level.")).toBeInTheDocument();

    await user.type(within(form).getByRole("textbox", { name: "Name" }), "Exports Desk");
    await user.click(within(form).getByRole("combobox", { name: "Level" }));
    await user.click(await screen.findByRole("option", { name: /^5 · / }));
    await user.click(
      within(form).getByRole("checkbox", { name: "A top-level office, under none" }),
    );
    await user.click(
      within(form).getByRole("checkbox", { name: "An HQ unit, covering no territory" }),
    );
    await user.click(within(form).getByRole("button", { name: "Add the office" }));

    expect(await screen.findByText("Exports Desk added")).toBeInTheDocument();
    await waitFor(() => {
      expect(mockDb.offices.find((office) => office.name === "Exports Desk")).toMatchObject({
        parent: null,
        territory: null,
        role_level: 5,
      });
    });
  });

  it("is read-only without masters.edit", async () => {
    signInAs("employee");
    show(<Masters />);
    expect(await screen.findByRole("list", { name: "Offices" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New office" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Close / })).not.toBeInTheDocument();
  });
});

describe("[MSTR-011] The office form's rules", () => {
  it("asks for a place and a territory, or says there is none", () => {
    expect(officeProblems("create", emptyOfficeDraft())).toEqual({
      name: "Enter the office's name.",
      level: "Choose the level.",
      parent: "Choose the office it sits under, or make it a top-level office.",
      territory: "Choose the territory it covers, or mark it an HQ unit.",
    });
    expect(
      officeProblems("edit", { ...emptyOfficeDraft(), name: "X", root: true, hq: true }),
    ).toEqual({});
  });

  it("sends only what changed", () => {
    const office = {
      id: "o-1",
      name: "Rajkot District",
      roleLevel: 2,
      parent: { id: "o-0", name: "Gujarat State" },
      territory: { id: "t-1", name: "Rajkot", level: "district" },
      isOpen: true,
      closedAt: null,
      activeUsers: 2,
    };
    expect(
      patchRequestOfOffice(office, {
        name: "Rajkot District ",
        level: "2",
        parent: office.parent,
        root: false,
        territory: office.territory,
        hq: false,
      }),
    ).toEqual({});
    expect(
      patchRequestOfOffice(office, {
        name: "Rajkot",
        level: "2",
        parent: null,
        root: true,
        territory: office.territory,
        hq: false,
      }),
    ).toEqual({ name: "Rajkot", parent_id: null });
  });
});
