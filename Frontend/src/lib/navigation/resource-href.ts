/**
 * A CRM record that a notification or a message points at. `type` stays a plain
 * string: a type the app has no screen for yet still renders, just without a link.
 */
export interface ResourceRef {
  readonly type: string;
  readonly id: string;
  /** Human reference from the backend, e.g. "Patel Farms · LD-26-10042". */
  readonly label: string;
}

const RESOURCE_TYPE_LABELS = new Map<string, string>([
  ["lead", "Lead"],
  ["quotation", "Quotation"],
  ["sales_order", "Sales order"],
  ["approval", "Approval"],
  ["task", "Task"],
  ["complaint", "Complaint"],
]);

/** "Lead", "Sales order" — or "Record" for a type the app does not know yet. */
export function describeResourceType(type: string): string {
  return RESOURCE_TYPE_LABELS.get(type) ?? "Record";
}

/**
 * The screens a record can open today. Spelled as template types (not `Route`) so typed
 * routes can check each one where it is passed to a link.
 */
export type ResourceHref = `/leads/${string}`;

/** Where a record opens, or null while its module has no screen yet. */
export function resourceHref(resource: Pick<ResourceRef, "type" | "id">): ResourceHref | null {
  if (resource.type === "lead") {
    return `/leads/${encodeURIComponent(resource.id)}`;
  }
  // TODO(QUOT-001): link quotations, sales orders, approvals, tasks and complaints as their screens land.
  return null;
}
