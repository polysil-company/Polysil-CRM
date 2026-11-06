import type { MarketingOrderWire, MaterialWire } from "@/features/marketing/api/marketing.schemas";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";

import { mockUuid } from "./reference";

/** The mock's own id space for marketing material rows. */
const MARKETING_SPACE = 0x3a7;

export function mockMarketingId(kind: number, index: number): string {
  return mockUuid(MARKETING_SPACE, kind * 10_000 + index);
}

/** An order as the mock keeps it: the wire shape without the caller's `can`. */
export type MockMarketingOrder = Omit<MarketingOrderWire, "can">;

/** The backend's 17-item catalogue (migration 038), at stand-in prices: all provisional. */
const CATALOGUE: readonly (readonly [string, string, string, string])[] = [
  ["MM-CANOPY-CAMP", "Canopy campaign", "Event", "15000.00"],
  ["MM-BIKE-CAMP", "Bike campaign", "Event", "12000.00"],
  ["MM-FARMER-MEET", "Farmer meeting", "Event", "8000.00"],
  ["MM-CAP", "POLYSIL CAP", "Nos", "120.00"],
  ["MM-UMBRELLA", "POLYSIL UMBRELLA", "Nos", "450.00"],
  ["MM-PEN", "POLYSIL PEN", "Nos", "15.00"],
  ["MM-KEYCHAIN", "POLYSIL KEYCHAIN", "Nos", "35.00"],
  ["MM-BAG", "POLYSIL BAG", "Nos", "260.00"],
  ["MM-NW-BAG", "POLYSIL NON WOVEN BAG", "Nos", "40.00"],
  ["MM-CANOPY", "POLYSIL CANOPY", "Nos", "6500.00"],
  ["MM-MEET-BANNER", "POLYSIL FARMER MEET BANNER", "Nos", "900.00"],
  ["MM-OFFICE-BANNER", "POLYSIL DEALER OFFICE BANNER", "Nos", "1500.00"],
  ["MM-DEALER-KIT", "POLYSIL DEALER KIT", "Nos", "2500.00"],
  ["MM-PROFILE", "POLYSIL COMPANY PROFILE LITERATURE", "Nos", "45.00"],
  ["MM-BROCHURE", "POLYSIL PRODUCT BROCHURE LITERATURE", "Nos", "20.00"],
  ["MM-DIARY-S", "POLYSIL DIARY SMALL", "Nos", "180.00"],
  ["MM-DIARY-B", "POLYSIL DIARY BIG", "Nos", "320.00"],
];

export function seedMaterials(): MaterialWire[] {
  return [
    ...CATALOGUE.map(([code, name, unit, price], index): MaterialWire => ({
      id: mockMarketingId(1, index + 1),
      code,
      name,
      description: null,
      unit,
      price,
      company_share_pct: "50.00",
      image_url: null,
      is_active: true,
      is_provisional: true,
    })),
    // One switched off, so the admin list shows the state.
    {
      id: mockMarketingId(1, 99),
      code: "MM-CALENDAR",
      name: "POLYSIL WALL CALENDAR",
      description: "Last year's calendar.",
      unit: "Nos",
      price: "60.00",
      company_share_pct: "50.00",
      image_url: null,
      is_active: false,
      is_provisional: false,
    },
  ];
}

const rupees = (paise: number): string => (paise / 100).toFixed(2);
const paise = (value: string): number => Math.round(Number(value) * 100);

/** A line's value and shares; an office's own use is all the company's. */
export function lineFor(
  material: MaterialWire,
  qty: number,
  lineIndex: number,
  officeUse: boolean,
  orderIndex: number,
): MockMarketingOrder["lines"][number] {
  const value = paise(material.price ?? "0") * qty;
  const pct = officeUse ? 100 : Number(material.company_share_pct ?? "0");
  const company = Math.round((value * pct) / 100);
  return {
    id: mockMarketingId(3, orderIndex * 100 + lineIndex),
    material: { id: material.id, code: material.code, name: material.name },
    unit: material.unit,
    qty,
    price: material.price ?? "0.00",
    value: rupees(value),
    company_share_pct: pct.toFixed(2),
    company_share: rupees(company),
    dealer_share: rupees(value - company),
  };
}

export function totalsOf(lines: MockMarketingOrder["lines"]): MockMarketingOrder["totals"] {
  const sum = (pick: (line: MockMarketingOrder["lines"][number]) => string): string =>
    rupees(lines.reduce((total, line) => total + paise(pick(line)), 0));
  return {
    value: sum((line) => line.value),
    company_share: sum((line) => line.company_share),
    dealer_share: sum((line) => line.dealer_share),
  };
}

export const MARKETING_DEALER = { id: "prt-201", name: "Shah Agro Traders" };
export const MARKETING_DEALER_USER = { id: "usr-201", name: "Bhavesh Shah" };
export const MARKETING_OFFICE = { id: "ou-rajkot", name: "Rajkot District Office" };
const OFFICER = { id: "usr-014", name: "Nikhil Rana" };
const DM = { id: "usr-007", name: "Pooja Mehta" };
const MARKETING_TEAM = { id: "usr-021", name: "Sneha Iyer" };

/**
 * Four orders: a dealer's waiting for the District Manager, an officer's for a dealer approved
 * and waiting to ship, an office's own use dispatched, and a dealer's refused.
 */
export function seedMarketingOrders(materials: readonly MaterialWire[]): MockMarketingOrder[] {
  const find = (code: string): MaterialWire => {
    const material = materials.find((item) => item.code === code);
    if (material === undefined) throw new Error(`No material ${code}`);
    return material;
  };
  const today = todayInIndia();
  const at = (days: number): string => `${shiftCalendarDay(today, -days)}T05:30:00.000Z`;
  const order = (
    index: number,
    partial: Omit<MockMarketingOrder, "id" | "order_no" | "totals" | "is_provisional">,
  ): MockMarketingOrder => ({
    id: mockMarketingId(2, index),
    order_no: `MM/GJ/2026-27/${String(index).padStart(5, "0")}`,
    totals: totalsOf(partial.lines),
    is_provisional: true,
    ...partial,
  });
  const lines = (
    index: number,
    items: readonly (readonly [string, number])[],
    officeUse = false,
  ): MockMarketingOrder["lines"] =>
    items.map(([code, qty], line) => lineFor(find(code), qty, line + 1, officeUse, index));

  return [
    order(4, {
      status: "submitted",
      partner: MARKETING_DEALER,
      requested_by: MARKETING_DEALER_USER,
      office: MARKETING_OFFICE,
      lines: lines(4, [
        ["MM-CAP", 50],
        ["MM-OFFICE-BANNER", 2],
        ["MM-BROCHURE", 200],
      ]),
      remark: "For the Diwali farmer meet at our shop.",
      decision: null,
      dispatch: null,
      cancel_remark: null,
      created_at: at(1),
    }),
    order(3, {
      status: "approved",
      partner: { id: "prt-202", name: "Patel Irrigation Store" },
      requested_by: OFFICER,
      office: MARKETING_OFFICE,
      lines: lines(3, [
        ["MM-DEALER-KIT", 1],
        ["MM-UMBRELLA", 10],
      ]),
      remark: null,
      decision: { status: "approved", by: DM, at: at(3), remark: null },
      dispatch: null,
      cancel_remark: null,
      created_at: at(4),
    }),
    order(2, {
      status: "dispatched",
      partner: null,
      requested_by: OFFICER,
      office: MARKETING_OFFICE,
      lines: lines(
        2,
        [
          ["MM-MEET-BANNER", 4],
          ["MM-PEN", 300],
        ],
        true,
      ),
      remark: "Anand farmer meeting.",
      decision: { status: "approved", by: DM, at: at(9), remark: "Go ahead." },
      dispatch: {
        dispatched_on: shiftCalendarDay(today, -7),
        reference: "DTDC 4471 2208",
        by: MARKETING_TEAM,
      },
      cancel_remark: null,
      created_at: at(10),
    }),
    order(1, {
      status: "rejected",
      partner: MARKETING_DEALER,
      requested_by: MARKETING_DEALER_USER,
      office: MARKETING_OFFICE,
      lines: lines(1, [["MM-CANOPY", 3]]),
      remark: null,
      decision: {
        status: "rejected",
        by: DM,
        at: at(15),
        remark: "One canopy per dealer this season.",
      },
      dispatch: null,
      cancel_remark: null,
      created_at: at(16),
    }),
  ];
}
