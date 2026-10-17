import type { CommissionWire, RateWire } from "@/features/commission/api/commission.schemas";

import { mockUuid } from "./reference";

/** The mock's own id space for commissions and their rates. */
const COMMISSION_SPACE = 0xc0a;
const RATE_SPACE = 0xc0b;

export function mockCommissionId(index: number): string {
  return mockUuid(COMMISSION_SPACE, index);
}

export function mockRateId(index: number): string {
  return mockUuid(RATE_SPACE, index);
}

/**
 * GGRC's rates (FS-033; every number a stand-in the admin sets): last year's scheme-wide rate,
 * this year's, and a higher one for dealers. A sub-dealer falls back to the scheme-wide rate.
 */
export function seedCommissionRates(): RateWire[] {
  const base = { scheme: "GGRC", system_type: null, partner: null };
  return [
    {
      ...base,
      id: mockRateId(3),
      partner_type: "dealer",
      commission_pct: "6.00",
      tod_pct: "2.00",
      effective_from: "2026-04-01",
    },
    {
      ...base,
      id: mockRateId(2),
      partner_type: null,
      commission_pct: "5.00",
      tod_pct: "2.00",
      effective_from: "2026-04-01",
    },
    {
      ...base,
      id: mockRateId(1),
      partner_type: null,
      commission_pct: "4.00",
      tod_pct: "1.00",
      effective_from: "2025-04-01",
    },
  ];
}

/** Rounds to paise, half up, as the backend's numeric(14,2) does. */
export function money(value: number): string {
  return (Math.round((value + Number.EPSILON) * 100) / 100).toFixed(2);
}

/** The figures the backend works out (migration 037's checks). */
export function workOutCommission(input: {
  costExclGst: number;
  gi: number;
  pvc: number;
  installation: number;
  todBase: number | null;
  commissionPct: number;
  todPct: number;
}): Pick<
  CommissionWire,
  "commission_base" | "commission_amount" | "tod_base" | "tod_amount" | "total"
> {
  const base = input.costExclGst - input.gi - input.pvc - input.installation;
  const todBase = input.todBase ?? base;
  const commission = Number(money((base * input.commissionPct) / 100));
  const tod = Number(money((todBase * input.todPct) / 100));
  return {
    commission_base: money(base),
    commission_amount: money(commission),
    tod_base: money(todBase),
    tod_amount: money(tod),
    total: money(commission + tod),
  };
}
