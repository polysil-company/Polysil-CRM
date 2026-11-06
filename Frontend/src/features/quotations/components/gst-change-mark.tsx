import type * as React from "react";

import { gstChangeNote } from "@/features/quotations/lib/quotation-labels";

/** QUOT-015 · A line's GST slab was picked over its HSN's: say so beside the rate. */
export function GstChangeMark({
  line,
}: {
  line: Parameters<typeof gstChangeNote>[0];
}): React.JSX.Element | null {
  const note = gstChangeNote(line);
  return note === null ? null : <span className="block text-xs text-warning">{note}</span>;
}
