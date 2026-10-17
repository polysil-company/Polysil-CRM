import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  adjustPoints,
  createRule,
  decideRedemption,
  getBalance,
  getLedger,
  patchRule,
  putRewardSettings,
  requestGift,
} from "@/features/rewards/api/rewards.api";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { RewardsPage } from "./rewards-page";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function show(searchParams = ""): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <RewardsPage />
      <Toaster />
    </>,
    { searchParams },
  );
  return user;
}

async function codeOf(call: Promise<unknown>): Promise<string | null> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error) ? (error.code ?? null) : null;
}

let keys = 0;
function key(): string {
  keys += 1;
  return `rewards-test-${String(keys)}`;
}

/** A seeded dealer staff can look up, with 430 points. */
const AMBIKA = "0000009a-0000-4000-8000-000000000006";

function giftNamed(name: string): string {
  const gift = mockDb.gifts.find((item) => item.name === name);
  if (gift === undefined) throw new Error(`No gift ${name}`);
  return gift.id;
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

describe("[RWD-001] Points and gifts — the contract", () => {
  afterEach(reset);

  it("gives a dealer its own balance and history, and a field officer only their own", async () => {
    writeMockRole("dealer");
    const balance = await getBalance({ kind: "me" });
    expect(balance).toMatchObject({ holder: { name: "Shah Agro Traders" }, points: 860 });
    const history = await getLedger({ kind: "me" }, null);
    expect(history.items[0]).toMatchObject({ kind: "redeemed", points: -400 });

    writeMockRole("employee");
    expect((await getBalance({ kind: "me" })).points).toBe(100);
    expect(await codeOf(getBalance({ kind: "partner", id: AMBIKA }))).toBe("not_found");

    writeMockRole("state_manager");
    expect((await getBalance({ kind: "partner", id: AMBIKA })).points).toBe(430);
  });

  it("holds the points for a gift, refuses one not covered, and gives them back on withdraw", async () => {
    writeMockRole("dealer");
    const asked = await requestGift({
      body: { gift_id: giftNamed("Branded cap") },
      idempotencyKey: key(),
    });
    expect(asked.status).toBe("pending");
    expect((await getBalance({ kind: "me" })).points).toBe(710);
    expect(
      await codeOf(
        requestGift({ body: { gift_id: giftNamed("Shop signboard") }, idempotencyKey: key() }),
      ),
    ).toBe("insufficient_points");

    await decideRedemption(asked.id, "withdraw", { body: { remark: null }, idempotencyKey: key() });
    expect((await getBalance({ kind: "me" })).points).toBe(860);
  });
});

describe("[RWD-002] Gift desk — the contract", () => {
  afterEach(reset);

  it("marks a gift sent, refuses one only with a reason (points back), and closes a decided one", async () => {
    writeMockRole("admin");
    const [waiting] = mockDb.rewardRedemptions.filter((row) => row.status === "pending");
    if (waiting === undefined) throw new Error("No waiting gift");
    expect(
      await codeOf(
        decideRedemption(waiting.id, "reject", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("remark_required");
    const refused = await decideRedemption(waiting.id, "reject", {
      body: { remark: "Out of stock this month" },
      idempotencyKey: key(),
    });
    expect(refused.status).toBe("rejected");
    expect(
      await codeOf(
        decideRedemption(waiting.id, "fulfil", { body: { remark: null }, idempotencyKey: key() }),
      ),
    ).toBe("redemption_closed");

    writeMockRole("dealer");
    expect((await getBalance({ kind: "me" })).points).toBe(1260);
  });
});

describe("[RWD-003] Reward admin — the contract", () => {
  afterEach(reset);

  it("keeps a used rule's terms, refuses a taken code, changes settings once a day, adjusts", async () => {
    writeMockRole("admin");
    const used = mockDb.rewardRules.find((rule) => rule.used);
    if (used === undefined) throw new Error("No used rule");
    expect(await codeOf(patchRule(used.id, { body: { points: 5 }, idempotencyKey: key() }))).toBe(
      "rule_in_use",
    );
    const ended = await patchRule(used.id, {
      body: { valid_to: "2027-03-31" },
      idempotencyKey: key(),
    });
    expect(ended.validTo).toBe("2027-03-31");

    const body = {
      code: "DEALER-ORDER",
      name: "Again",
      holder: "partner" as const,
      basis: "order_value" as const,
      points: 1,
      per_amount: "500",
      valid_from: "2026-11-01",
      valid_to: null,
      expiry_days: null,
    };
    expect(await codeOf(createRule({ body, idempotencyKey: key() }))).toBe("code_taken");

    const settings = await putRewardSettings({
      body: { point_value: "0.50", max_redeem_pct: "15" },
      idempotencyKey: key(),
    });
    expect(settings).toMatchObject({ pointValue: "0.50", maxRedeemPct: "15.00" });
    expect(
      await codeOf(
        putRewardSettings({
          body: { point_value: "1", max_redeem_pct: "10" },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("settings_changed_today");

    await adjustPoints({
      body: { partner_id: AMBIKA, user_id: null, points: -60, reason: "Duplicate credit" },
      idempotencyKey: key(),
    });
    expect((await getBalance({ kind: "partner", id: AMBIKA })).points).toBe(370);

    writeMockRole("dealer");
    expect(
      await codeOf(
        adjustPoints({
          body: { partner_id: "prt-201", user_id: null, points: 10, reason: "Me" },
          idempotencyKey: key(),
        }),
      ),
    ).toBe("forbidden");
  });
});

describe("[RWD-001] Points and gifts — the screen", () => {
  afterEach(reset);

  it("shows a dealer its balance and history, and asks for a gift it can afford", async () => {
    signInAs("dealer");
    const user = show();

    expect(await screen.findByText("860 points")).toBeInTheDocument();
    expect(screen.getByText(/Worth ₹860.00 on an order/)).toBeInTheDocument();
    const history = await screen.findByRole("list", { name: "Points history" });
    expect(within(history).getByText("Held for a gift: Steel water bottle")).toBeInTheDocument();
    // A dealer sees no staff tabs.
    expect(screen.queryByRole("tab", { name: "Gift desk" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Gifts" }));
    const gifts = await screen.findByRole("list", { name: "Gifts" });
    expect(
      await within(gifts).findByRole("button", { name: "Ask for Shop signboard" }),
    ).toBeDisabled();
    expect(within(gifts).getByText("1,640 more points needed.")).toBeInTheDocument();
    await user.click(within(gifts).getByRole("button", { name: "Ask for Branded cap" }));
    const dialog = await screen.findByRole("dialog", { name: "Ask for Branded cap?" });
    await user.click(within(dialog).getByRole("button", { name: "Ask for it" }));

    expect(await screen.findByText("Gift asked for")).toBeInTheDocument();
    const requests = await screen.findByRole("list", { name: "Your gift requests" });
    expect(await within(requests).findAllByText("Branded cap")).not.toHaveLength(0);
  });

  it("lets a manager look up a dealer's points", async () => {
    signInAs("state_manager");
    const user = show();
    expect(await screen.findByText("100 points")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Whose points"), "Ambika");
    await user.click(await screen.findByRole("option", { name: /Ambika Krishi Kendra/ }));
    expect(await screen.findByText("430 points")).toBeInTheDocument();
  });
});

describe("[RWD-002] Gift desk — the screen", () => {
  afterEach(reset);

  it("refuses a waiting gift with a reason", async () => {
    signInAs("admin");
    const user = show("?tab=desk");
    const list = await screen.findByRole("list", { name: "Gift requests" });
    await user.click(within(list).getByRole("button", { name: /^Refuse Steel water bottle/ }));
    const dialog = await screen.findByRole("dialog", { name: "Refuse the gift?" });
    await user.click(within(dialog).getByRole("button", { name: "Refuse" }));
    expect(await within(dialog).findByText("Say why.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Why"), "Out of stock this month");
    await user.click(within(dialog).getByRole("button", { name: "Refuse" }));

    expect(await screen.findByText("Gift refused")).toBeInTheDocument();
    expect(await screen.findByText("Nothing waiting")).toBeInTheDocument();
  });
});

describe("[RWD-003] Reward admin — the screen", () => {
  afterEach(reset);

  it("adds an earning rule, naming what is missing first", async () => {
    signInAs("admin");
    const user = show("?tab=rules");
    await user.click(await screen.findByRole("button", { name: "Add a rule" }));
    const dialog = await screen.findByRole("dialog", { name: "Add an earning rule" });
    await user.click(within(dialog).getByRole("button", { name: "Add rule" }));
    expect(await within(dialog).findByText("Name it.")).toBeInTheDocument();
    expect(within(dialog).getByText("Whole points, at least 1.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Code"), "monsoon-x");
    await user.type(within(dialog).getByLabelText("Name"), "Monsoon extra");
    await user.type(within(dialog).getByLabelText("Points"), "2");
    await user.type(within(dialog).getByLabelText("For every ₹"), "1000");
    await user.click(within(dialog).getByRole("button", { name: "Add rule" }));

    expect(await screen.findByText("Rule added")).toBeInTheDocument();
    expect(mockDb.rewardRules[0]).toMatchObject({ code: "MONSOON-X", per_amount: "1000.00" });
  });

  it("changes the point value from today", async () => {
    signInAs("admin");
    const user = show("?tab=settings");
    const form = await screen.findByRole("form", { name: "Point settings" });
    const value = within(form).getByLabelText("One point is worth");
    await user.clear(value);
    await user.type(value, "0.50");
    await user.click(within(form).getByRole("button", { name: "Save from today" }));
    expect(await screen.findByText("Point settings changed")).toBeInTheDocument();
  });

  it("adjusts a dealer's points with a reason", async () => {
    signInAs("admin");
    const user = show();
    await user.type(await screen.findByLabelText("Whose points"), "Ambika");
    await user.click(await screen.findByRole("option", { name: /Ambika Krishi Kendra/ }));
    expect(await screen.findByText("430 points")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Adjust points" }));
    const dialog = await screen.findByRole("dialog", { name: "Adjust points" });
    await user.type(within(dialog).getByLabelText("Points"), "-60");
    expect(within(dialog).getByText("The balance becomes 370 points.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Reason"), "Duplicate credit");
    await user.click(within(dialog).getByRole("button", { name: "Adjust" }));

    expect(await screen.findByText("Points adjusted")).toBeInTheDocument();
    expect(await screen.findByText("370 points")).toBeInTheDocument();
  });
});
