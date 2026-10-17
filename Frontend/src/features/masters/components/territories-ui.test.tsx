import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  createTerritory,
  listTerritories,
  patchTerritory,
} from "@/features/masters/api/masters.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { Masters } from "./masters";

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
    { searchParams: "?tab=territories" },
  );
  return user;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

async function state(name: string): Promise<{ id: string; codeLocked: boolean }> {
  const page = await listTerritories({ level: "state", parentId: null, q: name, cursor: null });
  const found = page.items.find((item) => item.name === name);
  if (found === undefined) throw new Error(`No state ${name}`);
  return found;
}

describe("[MSTR-012] Territories, through the API", () => {
  afterEach(reset);

  it("locks a state's code once its leads are numbered, and keeps others open", async () => {
    signInAs("admin");
    const gujarat = await state("Gujarat");
    expect(gujarat.codeLocked).toBe(true);
    expect((await state("Uttar Pradesh")).codeLocked).toBe(false);

    await expect(patchTerritory(gujarat.id, { code: "GU" })).rejects.toMatchObject({
      status: 422,
      details: { fields: { code: expect.any(String) } },
    });
    const renamed = await patchTerritory(gujarat.id, { name: "Gujarat State" });
    expect(renamed).toMatchObject({ name: "Gujarat State", code: "GJ" });
  });

  it("adds one under the level above, with unique names and codes", async () => {
    signInAs("admin");
    const up = await state("Uttar Pradesh");
    await expect(
      createTerritory({ name: "Bareilly", level: "district", parent_id: null, code: null }),
    ).rejects.toMatchObject({
      status: 422,
      details: { fields: { parent_id: expect.any(String) } },
    });

    const district = await createTerritory({
      name: "Bareilly",
      level: "district",
      parent_id: up.id,
      code: "brl",
    });
    expect(district).toMatchObject({ code: "BRL", parent: { id: up.id } });
    await expect(
      createTerritory({ name: "bareilly", level: "district", parent_id: up.id, code: null }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { name: expect.any(String) } } });

    signInAs("employee");
    await expect(
      createTerritory({ name: "Rajasthan", level: "state", parent_id: null, code: "RJ" }),
    ).rejects.toMatchObject({ status: 403 });
  });
});

describe("[MSTR-012] The Territories tab", () => {
  afterEach(reset);

  it("lists the states, opens one's districts, and says which code is locked", async () => {
    signInAs("admin");
    const user = show(<Masters />);

    const list = await screen.findByRole("list", { name: "Territories" });
    const gujarat = within(list)
      .getAllByRole("listitem")
      .find((row) => within(row).queryByText("Gujarat") !== null);
    if (gujarat === undefined) throw new Error("No Gujarat row");
    expect(within(gujarat).getByText(/can't change/)).toBeInTheDocument();

    await user.click(within(gujarat).getByRole("button", { name: "Districts in Gujarat" }));
    // Every district row says "In Gujarat"; how many are drawn by now depends on timing.
    expect((await screen.findAllByText("In Gujarat")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Rajkot")).toBeInTheDocument();
  });

  it("adds a state with its code, and refuses to change a locked one", async () => {
    signInAs("admin");
    const user = show(<Masters />);

    await user.click(await screen.findByRole("button", { name: "New territory" }));
    const form = await screen.findByRole("form", { name: "New territory" });
    await user.click(within(form).getByRole("radio", { name: "State" }));
    await user.type(within(form).getByRole("textbox", { name: "Name" }), "Rajasthan");
    await user.type(within(form).getByRole("textbox", { name: /^Code/ }), "rj");
    await user.click(within(form).getByRole("button", { name: "Add territory" }));
    expect(await screen.findByText("Rajasthan added")).toBeInTheDocument();
    expect(await screen.findByText("RJ")).toBeInTheDocument();

    const list = screen.getByRole("list", { name: "Territories" });
    await user.click(within(list).getByRole("button", { name: "Edit Gujarat" }));
    const edit = await screen.findByRole("form", { name: "Edit Gujarat" });
    expect(within(edit).getByRole("textbox", { name: /^Code/ })).toBeDisabled();
  });

  it("lets anyone who sees Masters read, and only an editor add", async () => {
    signInAs("employee");
    show(<Masters />);

    expect(await screen.findByRole("list", { name: "Territories" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New territory" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit / })).not.toBeInTheDocument();
  });
});
