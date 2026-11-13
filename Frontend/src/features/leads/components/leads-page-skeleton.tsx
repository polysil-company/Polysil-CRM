import type * as React from "react";

import { LeadsTableSkeleton } from "./leads-table";
import { LeadsToolbarSkeleton } from "./leads-toolbar";

/** Loading state of the whole leads page body: toolbar + table. */
export function LeadsPageSkeleton(): React.JSX.Element {
  return (
    <>
      <LeadsToolbarSkeleton />
      <LeadsTableSkeleton />
    </>
  );
}
