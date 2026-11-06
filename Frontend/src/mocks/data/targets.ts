import { shiftMonth, todayInIndia } from "@/lib/format";

import { MOCK_TEAM } from "./tasks";

/** One change to a person's target for a month; the latest per measure counts (TGT-002). */
export interface MockTargetEntry {
  readonly userId: string;
  readonly month: string;
  readonly metric: string;
  readonly value: string | number;
  readonly setBy: { readonly id: string; readonly full_name: string };
  readonly setAt: string;
}

const SETTER = { id: "usr-001", full_name: "Aarav Desai" };

/** Targets for this month and the last, for most of the team; one person has none yet. */
export function seedTargets(now: Date = new Date()): MockTargetEntry[] {
  const thisMonth = todayInIndia(now).slice(0, 7);
  const lastMonth = shiftMonth(thisMonth, -1);
  const setAt = `${thisMonth}-01T05:00:00.000Z`;
  const entries: MockTargetEntry[] = [];
  MOCK_TEAM.slice(0, -1).forEach((person, index) => {
    for (const month of [lastMonth, thisMonth]) {
      const at = month === thisMonth ? setAt : `${lastMonth}-01T05:00:00.000Z`;
      entries.push(
        {
          userId: person.id,
          month,
          metric: "order_value",
          value: `${String(300000 + index * 100000)}.00`,
          setBy: SETTER,
          setAt: at,
        },
        { userId: person.id, month, metric: "orders", value: 4 + index, setBy: SETTER, setAt: at },
        {
          userId: person.id,
          month,
          metric: "leads_won",
          value: 3 + (index % 3),
          setBy: SETTER,
          setAt: at,
        },
      );
    }
  });
  return entries;
}
