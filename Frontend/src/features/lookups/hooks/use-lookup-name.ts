"use client";

import { useQuery } from "@tanstack/react-query";

import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import type { LookupList } from "@/features/lookups/api/lookups.schemas";
import { findLookupName } from "@/features/lookups/lib/lookup-labels";

/**
 * MSTR-002 · The name for a code in one of the admin-edited lists ("agri_fair" → "Agri Fair").
 * Every caller shares one cached request per list; until it arrives, or if it fails, the
 * code is shown in readable form instead.
 */
export function useLookupName(list: LookupList, code: string): string {
  const { data } = useQuery(lookupListQueryOptions(list));
  return findLookupName(data, code);
}
