import type { EntitlementWire, SchemeWire } from "@/features/schemes/api/schemes.schemas";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";

import { mockUuid } from "./reference";
import { MOCK_TERRITORIES } from "./territories";

/** The mock's own id space for schemes and their credits. */
const SCHEME_SPACE = 0x5c4e;
const CREDIT_SPACE = 0x5c4f;

export function mockSchemeId(index: number): string {
  return mockUuid(SCHEME_SPACE, index);
}

/** A seeded scheme, as the backend stores it (FS-031). */
function scheme(
  index: number,
  fields: Omit<SchemeWire, "id" | "is_current" | "created_at">,
  today: string,
): SchemeWire {
  const current =
    fields.is_active &&
    fields.valid_from <= today &&
    (fields.valid_to === null || fields.valid_to >= today);
  return {
    id: mockSchemeId(index),
    ...fields,
    is_current: current,
    created_at: `${fields.valid_from}T04:30:00.000Z`,
  };
}

/**
 * Six schemes, one or more of each type, running, scheduled and ended, some already given:
 * enough to see every state on the list and every rule on the form.
 */
export function seedSchemes(productId: string | null, now: Date = new Date()): SchemeWire[] {
  const today = todayInIndia(now);
  const day = (days: number): string => shiftCalendarDay(today, days);
  const gujarat = MOCK_TERRITORIES.find((territory) => territory.level === "state");
  const rajkot = MOCK_TERRITORIES.find(
    (territory) => territory.level === "district" && territory.name === "Rajkot",
  );
  const none = { cap: null, entitlement_days: null };
  return [
    scheme(
      1,
      {
        code: "GJ-DRIP-5",
        name: "Gujarat drip 5% above 2 lakh",
        description: "For dealers in Gujarat, on drip orders of two lakh rupees or more.",
        scheme_type: "order_discount",
        condition: { metric: "order_value", min: "200000.000", max: null },
        benefit: { kind: "pct", value: "5.000", cap: "50000.00", entitlement_days: null },
        period: null,
        valid_from: day(-10),
        valid_to: day(75),
        priority: 100,
        stackable: false,
        is_active: true,
        used: true,
        targets: [
          ...(gujarat === undefined ? [] : [{ type: "territory" as const, id: gujarat.id }]),
          { type: "partner_type", id: "dealer" },
        ],
      },
      today,
    ),
    scheme(
      2,
      {
        code: "MONSOON-PTS",
        name: "Monsoon points",
        description: null,
        scheme_type: "order_points",
        condition: { metric: "order_value", min: "100000.000", max: null },
        benefit: { kind: "points", value: "200.000", ...none },
        period: null,
        valid_from: day(-30),
        valid_to: day(30),
        priority: 100,
        stackable: true,
        is_active: true,
        used: false,
        targets: [],
      },
      today,
    ),
    scheme(
      3,
      {
        code: "NEXT-3K",
        name: "₹3,000 off the next order",
        description: "Earned when an order of one and a half lakh or more is delivered.",
        scheme_type: "next_order",
        condition: { metric: "order_value", min: "150000.000", max: null },
        benefit: { kind: "flat", value: "3000.000", cap: null, entitlement_days: 90 },
        period: null,
        valid_from: day(-20),
        valid_to: null,
        priority: 50,
        stackable: false,
        is_active: true,
        used: true,
        targets: [
          { type: "partner_type", id: "dealer" },
          { type: "partner_type", id: "sub_dealer" },
        ],
      },
      today,
    ),
    scheme(
      4,
      {
        code: "FESTIVE-TARGET",
        name: "Festive monthly target",
        description:
          "2% back as a credit when a dealer's delivered orders in the month reach five lakh.",
        scheme_type: "period",
        condition: { metric: "order_value", min: "500000.000", max: null },
        benefit: { kind: "pct", value: "2.000", cap: null, entitlement_days: 60 },
        period: "month",
        valid_from: day(-40),
        valid_to: day(50),
        priority: 100,
        stackable: true,
        is_active: true,
        used: false,
        targets: [
          { type: "partner_type", id: "dealer" },
          ...(rajkot === undefined ? [] : [{ type: "territory" as const, id: rajkot.id }]),
        ],
      },
      today,
    ),
    scheme(
      5,
      {
        code: "SUMMER-5K",
        name: "Summer ₹5,000 off",
        description: null,
        scheme_type: "order_discount",
        condition: { metric: "order_value", min: "300000.000", max: null },
        benefit: { kind: "flat", value: "5000.000", ...none },
        period: null,
        valid_from: day(-200),
        valid_to: day(-100),
        priority: 100,
        stackable: false,
        is_active: true,
        used: true,
        targets: [],
      },
      today,
    ),
    scheme(
      6,
      {
        code: "LATERAL-3",
        name: "3% credit on laterals",
        description: null,
        scheme_type: "next_order",
        condition: { metric: "product_qty", min: "500.000", max: null },
        benefit: { kind: "pct", value: "3.000", cap: "10000.00", entitlement_days: null },
        period: null,
        valid_from: day(10),
        valid_to: day(100),
        priority: 200,
        stackable: false,
        is_active: true,
        used: false,
        targets: productId === null ? [] : [{ type: "product", id: productId }],
      },
      today,
    ),
  ];
}

/** Credits for the demo dealer (Shah Agro Traders) and one other, in each state. */
export function seedEntitlements(
  order: { id: string; order_no: string | null } | null,
  now: Date = new Date(),
): EntitlementWire[] {
  const today = todayInIndia(now);
  const at = (days: number): string => `${shiftCalendarDay(today, days)}T06:00:00.000Z`;
  const ref = { id: mockSchemeId(3), code: "NEXT-3K", name: "₹3,000 off the next order" };
  const festive = { id: mockSchemeId(4), code: "FESTIVE-TARGET", name: "Festive monthly target" };
  const shah = { id: "prt-201", name: "Shah Agro Traders" };
  const base = {
    kind: "flat" as const,
    value: "3000.00",
    cap: null,
    period_start: null,
    period_end: null,
    consumed_order: null,
  };
  return [
    {
      id: mockUuid(CREDIT_SPACE, 1),
      scheme: ref,
      partner: shah,
      ...base,
      status: "available",
      earned_at: at(-4),
      expires_at: at(86),
      source_order: order,
    },
    {
      id: mockUuid(CREDIT_SPACE, 2),
      scheme: festive,
      partner: shah,
      ...base,
      kind: "pct",
      value: "2.00",
      status: "available",
      earned_at: at(-15),
      expires_at: at(45),
      source_order: null,
      period_start: shiftCalendarDay(today, -45),
      period_end: shiftCalendarDay(today, -16),
    },
    {
      id: mockUuid(CREDIT_SPACE, 3),
      scheme: ref,
      partner: shah,
      ...base,
      status: "consumed",
      earned_at: at(-18),
      expires_at: at(72),
      source_order: null,
      consumed_order: order,
    },
    {
      id: mockUuid(CREDIT_SPACE, 4),
      scheme: ref,
      partner: { id: "prt-202", name: "Patel Irrigation Point" },
      ...base,
      status: "expired",
      earned_at: at(-120),
      expires_at: at(-30),
      source_order: null,
    },
  ];
}
