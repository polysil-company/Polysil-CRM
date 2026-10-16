import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { getAchievement, getPersonTargets, setTargets } from "@/features/targets/api/targets.api";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { formatMonth, shiftMonth, todayInIndia } from "@/lib/format";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TEAM } from "@/mocks/data/tasks";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { TargetsView } from "./targets-view";

const THIS_MONTH = todayInIndia().slice(0, 7);
const NEXT_MONTH = shiftMonth(THIS_MONTH, 1);
const LAST_MONTH = shiftMonth(THIS_MONTH, -1);

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(ui: React.JSX.Element, searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      {ui}
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function teammate(index: number): { id: string; full_name: string } {
  const person = MOCK_TEAM[index];
  if (person === undefined) throw new Error("no seeded teammate");
  return person;
}

describe("[TGT-001] Achievement, through the API", () => {
  afterEach(reset);

  it("lists a field officer alone, and a manager with the team below", async () => {
    signInAs("employee");
    const own = await getAchievement(THIS_MONTH);
    expect(own.rows).toHaveLength(1);
    expect(own.rows[0]?.metrics.visits.achieved).toBeNull();

    signInAs("state_manager");
    const team = await getAchievement(THIS_MONTH);
    expect(team.rows).toHaveLength(MOCK_TEAM.length + 1);
    expect(team.saleCountedAt).toBe("approval");
    const seeded = team.rows.find((row) => row.user.id === teammate(0).id);
    expect(seeded?.metrics.orders.target).toBe(4);

    signInAs("dealer");
    await expect(getAchievement(THIS_MONTH)).rejects.toMatchObject({ status: 403 });
  });
});

describe("[TGT-002] Setting targets, through the API", () => {
  afterEach(reset);

  it("sets a teammate's targets with their history, and refuses what the backend refuses", async () => {
    signInAs("state_manager");
    const person = teammate(1);
    const saved = await setTargets({
      body: {
        user_id: person.id,
        month: NEXT_MONTH,
        targets: { orders: 9, order_value: "450000" },
      },
      idempotencyKey: "key-1",
    });
    expect(saved.targets).toMatchObject({ orders: 9, orderValue: "450000.00", visits: null });
    expect(saved.history).toHaveLength(2);
    expect((await getPersonTargets(person.id, NEXT_MONTH)).targets.orders).toBe(9);

    const me = mockMeFor("state_manager").data.id;
    await expect(
      setTargets({
        body: { user_id: me, month: THIS_MONTH, targets: { orders: 1 } },
        idempotencyKey: "k2",
      }),
    ).rejects.toMatchObject({ status: 403, code: "not_your_team" });
    await expect(
      setTargets({
        body: { user_id: person.id, month: LAST_MONTH, targets: { orders: 1 } },
        idempotencyKey: "k3",
      }),
    ).rejects.toMatchObject({ status: 422, code: "month_closed" });
    await expect(
      setTargets({
        body: { user_id: person.id, month: THIS_MONTH, targets: { orders: 2.5 } },
        idempotencyKey: "k4",
      }),
    ).rejects.toMatchObject({ status: 422, details: { fields: { orders: "a whole number" } } });

    signInAs("admin");
    const past = await setTargets({
      body: { user_id: person.id, month: LAST_MONTH, targets: { visits: 40 } },
      idempotencyKey: "k5",
    });
    expect(past.targets.visits).toBe(40);

    signInAs("employee");
    await expect(
      setTargets({
        body: { user_id: person.id, month: THIS_MONTH, targets: { orders: 1 } },
        idempotencyKey: "k6",
      }),
    ).rejects.toMatchObject({ status: 403 });
  });
});

describe("[TGT-001] TargetsView", () => {
  afterEach(reset);

  it("shows a field officer their own month, with nothing to set", async () => {
    signInAs("employee");
    show(<TargetsView />);
    expect(await screen.findByRole("heading", { name: "Your month" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: formatMonth(THIS_MONTH) })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Set targets/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("No target set")).toHaveLength(4);
  });

  it("moves between months from the URL", async () => {
    signInAs("employee");
    const user = show(<TargetsView />);
    await screen.findByRole("heading", { name: "Your month" });
    await user.click(screen.getByRole("button", { name: "Next month" }));
    expect(
      await screen.findByRole("heading", { name: formatMonth(NEXT_MONTH) }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "This month" }));
    expect(
      await screen.findByRole("heading", { name: formatMonth(THIS_MONTH) }),
    ).toBeInTheDocument();
  });
});

describe("[TGT-002] Set targets", () => {
  afterEach(reset);

  it("checks a value, then saves only what changed and clears an emptied target", async () => {
    signInAs("state_manager");
    const person = teammate(0);
    const user = show(<TargetsView />);

    await user.click(
      await screen.findByRole("button", { name: `Set targets for ${person.full_name}` }),
    );
    const dialog = await screen.findByRole("dialog");
    const orders = await within(dialog).findByLabelText("Orders");
    expect(orders).toHaveValue("4");
    expect(within(dialog).getByText("Changes to these targets")).toBeInTheDocument();

    await user.clear(orders);
    await user.type(orders, "2.5");
    await user.click(within(dialog).getByRole("button", { name: "Save targets" }));
    expect(await within(dialog).findByText("A whole number.")).toBeInTheDocument();

    await user.clear(orders);
    await user.type(orders, "9");
    await user.clear(within(dialog).getByLabelText("Leads won"));
    expect(within(dialog).getByText("Saving clears this target.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Save targets" }));

    expect(await screen.findByText(`Targets set for ${person.full_name}`)).toBeInTheDocument();
    const saved = await getPersonTargets(person.id, THIS_MONTH);
    expect(saved.targets).toMatchObject({ orders: 9, leadsWon: 0 });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("warns that a past month is closed, and shows the refusal", async () => {
    signInAs("state_manager");
    const person = teammate(0);
    const user = show(<TargetsView />, `?month=${LAST_MONTH}`);

    await user.click(
      await screen.findByRole("button", { name: `Set targets for ${person.full_name}` }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/This month has passed/)).toBeInTheDocument();
    const orders = await within(dialog).findByLabelText("Orders");
    await user.clear(orders);
    await user.type(orders, "6");
    await user.click(within(dialog).getByRole("button", { name: "Save targets" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Only an administrator changes a past month's targets.",
    );
  });
});
