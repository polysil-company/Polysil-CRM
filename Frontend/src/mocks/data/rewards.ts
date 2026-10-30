import type {
  GiftWire,
  LedgerRowWire,
  RedemptionWire,
  RewardSettingsWire,
  RuleWire,
} from "@/features/rewards/api/rewards.schemas";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";

import { mockUuid } from "./reference";

/** The mock's own id space for reward rows. */
const REWARD_SPACE = 0x2ed;

export function mockRewardId(kind: number, index: number): string {
  return mockUuid(REWARD_SPACE, kind * 10_000 + index);
}

/** Whose points a ledger row moves: a partner, or a staff user. */
export interface MockHolder {
  readonly type: "partner" | "user";
  readonly id: string;
  readonly name: string;
}

export interface MockLedgerEntry {
  readonly holder: MockHolder;
  readonly row: LedgerRowWire;
}

export const SHAH: MockHolder = { type: "partner", id: "prt-201", name: "Shah Agro Traders" };
/** Every mock staff role signs in as this user. */
export const STAFF_ME: MockHolder = { type: "user", id: "usr-001", name: "Aarav Desai" };

/** The earning rules (FS-032; every number a stand-in the admin sets). */
export function seedRewardRules(now: Date = new Date()): RuleWire[] {
  const today = todayInIndia(now);
  return [
    {
      id: mockRewardId(1, 1),
      code: "DEALER-ORDER",
      name: "1 point per ₹1,000 delivered",
      holder: "partner",
      basis: "order_value",
      points: 1,
      per_amount: "1000.00",
      valid_from: "2026-04-01",
      valid_to: null,
      expiry_days: 365,
      is_active: true,
      used: true,
    },
    {
      id: mockRewardId(1, 2),
      code: "LEAD-WON",
      name: "50 points for each lead won",
      holder: "staff",
      basis: "lead_won",
      points: 50,
      per_amount: null,
      valid_from: "2026-04-01",
      valid_to: null,
      expiry_days: null,
      is_active: true,
      used: true,
    },
    {
      id: mockRewardId(1, 3),
      code: "DIWALI-2X",
      name: "Diwali: 2 points per ₹1,000",
      holder: "partner",
      basis: "order_value",
      points: 2,
      per_amount: "1000.00",
      valid_from: shiftCalendarDay(today, 5),
      valid_to: shiftCalendarDay(today, 35),
      expiry_days: 180,
      is_active: true,
      used: false,
    },
  ];
}

/** One rupee a point, at most 10% of an order (migration 036's seed). */
export function seedRewardSettings(): RewardSettingsWire[] {
  return [{ point_value: "1.00", max_redeem_pct: "10.00", effective_from: "2026-04-01" }];
}

export function seedGifts(): GiftWire[] {
  return [
    {
      id: mockRewardId(2, 1),
      name: "Branded cap",
      description: "Polysil cotton cap.",
      points_cost: 150,
      is_active: true,
    },
    {
      id: mockRewardId(2, 2),
      name: "Steel water bottle",
      description: null,
      points_cost: 400,
      is_active: true,
    },
    {
      id: mockRewardId(2, 3),
      name: "Shop signboard",
      description: "A lit signboard with the dealer's name, fitted at the shop.",
      points_cost: 2500,
      is_active: true,
    },
    {
      id: mockRewardId(2, 4),
      name: "Wall clock",
      description: null,
      points_cost: 300,
      is_active: false,
    },
  ];
}

function at(today: string, days: number): string {
  return `${shiftCalendarDay(today, days)}T06:30:00.000Z`;
}

/**
 * Histories for the demo dealer (the dealer user's partner), a seeded dealer staff can look up,
 * and the signed-in staff user.
 */
export function seedLedger(
  seededDealer: MockHolder | null,
  now: Date = new Date(),
): MockLedgerEntry[] {
  const today = todayInIndia(now);
  let index = 0;
  const entry = (
    holder: MockHolder,
    days: number,
    points: number,
    kind: LedgerRowWire["kind"],
    reason: string,
    expires: number | null = null,
  ): MockLedgerEntry => {
    index += 1;
    return {
      holder,
      row: {
        id: mockRewardId(3, index),
        points,
        kind,
        reason,
        at: at(today, days),
        expires_at: expires === null ? null : at(today, days + expires),
      },
    };
  };
  // Newest first, as the ledger answers.
  return [
    entry(SHAH, -2, -400, "redeemed", "Held for a gift: Steel water bottle"),
    entry(SHAH, -9, 240, "earned", "Order SO/GJ/2026-27/00003 delivered", 365),
    entry(SHAH, -20, -60, "reversed", "Dispatch voided on SO/GJ/2026-27/00001"),
    entry(SHAH, -31, 980, "earned", "Order SO/GJ/2026-27/00001 delivered", 365),
    entry(SHAH, -58, -150, "redeemed", "Held for a gift: Branded cap"),
    entry(SHAH, -60, 250, "adjusted", "Opening balance carried over from the old scheme"),
    ...(seededDealer === null
      ? []
      : [
          entry(seededDealer, -12, 310, "earned", "Order SO/GJ/2026-27/00003 delivered", 365),
          entry(seededDealer, -40, 120, "earned", "Order SO/GJ/2026-27/00002 delivered", 365),
        ]),
    entry(STAFF_ME, -6, 50, "earned", "Lead won: POL/GJ/2026-27/00142"),
    entry(STAFF_ME, -18, 50, "earned", "Lead won: POL/GJ/2026-27/00118"),
  ];
}

/** One gift waiting at the desk, and one already sent. */
export function seedRedemptions(
  gifts: readonly GiftWire[],
  now: Date = new Date(),
): RedemptionWire[] {
  const today = todayInIndia(now);
  const bottle = gifts.find((gift) => gift.name === "Steel water bottle") ?? null;
  const cap = gifts.find((gift) => gift.name === "Branded cap") ?? null;
  const holder = { type: SHAH.type, id: SHAH.id, name: SHAH.name };
  return [
    {
      id: mockRewardId(4, 2),
      kind: "gift",
      holder,
      points: bottle?.points_cost ?? 400,
      amount: null,
      status: "pending",
      gift: bottle,
      sales_order: null,
      remark: null,
      decided_at: null,
      created_at: at(today, -2),
    },
    {
      id: mockRewardId(4, 1),
      kind: "gift",
      holder,
      points: cap?.points_cost ?? 150,
      amount: null,
      status: "fulfilled",
      gift: cap,
      sales_order: null,
      remark: "Sent with the October dispatch.",
      decided_at: at(today, -50),
      created_at: at(today, -58),
    },
  ];
}
