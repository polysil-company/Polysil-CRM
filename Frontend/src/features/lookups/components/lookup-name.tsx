"use client";

import type * as React from "react";

import type { LookupList } from "@/features/lookups/api/lookups.schemas";
import { useLookupName } from "@/features/lookups/hooks/use-lookup-name";

export interface LookupNameProps {
  list: LookupList;
  code: string;
}

/** MSTR-002 · Renders the name for a lookup code, for table cells and detail rows. */
export function LookupName({ list, code }: LookupNameProps): React.JSX.Element {
  return <>{useLookupName(list, code)}</>;
}
