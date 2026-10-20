import { queryOptions } from "@tanstack/react-query";

import { listHolidays } from "./holidays.api";

export const holidayKeys = {
  all: ["holidays"] as const,
  year: (year: number) => [...holidayKeys.all, year] as const,
};

/** MSTR-019 · A year's holidays. */
export function holidaysQueryOptions(year: number) {
  return queryOptions({
    queryKey: holidayKeys.year(year),
    queryFn: ({ signal }) => listHolidays(year, signal),
    meta: { dataId: "MSTR-019" },
  });
}
