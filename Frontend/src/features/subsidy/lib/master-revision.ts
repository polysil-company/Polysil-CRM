/**
 * SUBS-012 · Turning edits on a master table into a revision's rows. Values stay the strings
 * the administrator typed; an emptied optional figure becomes null. Only rows whose figures
 * changed are sent, so the rest stay as they are on the backend.
 */

export interface EditableField {
  /** The row's field this edits. */
  readonly key: string;
  readonly label: string;
  /** A decimal with at most these places; text when absent. */
  readonly places?: number;
  /** Empty means null for an optional figure; a required one must be filled. */
  readonly required: boolean;
  /** Bounds a percentage, e.g. 100. */
  readonly max?: number;
  /** A whole number, e.g. a pipe size in millimetres. */
  readonly integer?: boolean;
  /** A choice among these, e.g. the system or the unit; empty means none when optional. */
  readonly options?: readonly { readonly value: string; readonly label: string }[];
}

/** Row id → field key → typed value. */
export type Edits = Readonly<Record<string, Readonly<Record<string, string>>>>;

/** What a field should hold as typed, or why not; null when it reads right. */
export function editProblem(field: EditableField, value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") {
    if (!field.required) return null;
    return field.options === undefined
      ? `Enter the ${field.label.toLowerCase()}.`
      : `Choose the ${field.label.toLowerCase()}.`;
  }
  if (field.options !== undefined) {
    return field.options.some((option) => option.value === trimmed)
      ? null
      : "Choose one of the list.";
  }
  if (field.integer === true) {
    if (!/^\d+$/.test(trimmed)) return "Enter a whole number.";
    return field.max !== undefined && Number(trimmed) > field.max
      ? `At most ${String(field.max)}.`
      : null;
  }
  if (field.places === undefined) return trimmed.length > 300 ? "Up to 300 characters." : null;
  if (!/^\d+(\.\d+)?$/.test(trimmed)) return "Enter a number, like 12.50.";
  if ((trimmed.split(".")[1]?.length ?? 0) > field.places) {
    return `At most ${String(field.places)} decimal${field.places === 1 ? "" : "s"}.`;
  }
  if (field.max !== undefined && Number(trimmed) > field.max) {
    return `At most ${String(field.max)}.`;
  }
  return null;
}

/** The value a field holds now, as a string; null shows as empty. */
export function currentValue(row: Readonly<Record<string, unknown>>, key: string): string {
  const value = row[key];
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return "";
}

/** The typed value of a field, falling back to what the row holds. */
export function editedValue(
  edits: Edits,
  row: Readonly<Record<string, unknown>> & { readonly id: string },
  key: string,
): string {
  return edits[row.id]?.[key] ?? currentValue(row, key);
}

/** Rows whose editable figures differ from what they hold now. */
export function changedRowIds(
  rows: readonly (Readonly<Record<string, unknown>> & { readonly id: string })[],
  fields: readonly EditableField[],
  edits: Edits,
): string[] {
  return rows
    .filter((row) =>
      fields.some(
        (field) => editedValue(edits, row, field.key).trim() !== currentValue(row, field.key),
      ),
    )
    .map((row) => row.id);
}

/** A field as a revision sends it: a trimmed string, or null when an optional one is empty. */
export function sentValue(field: EditableField, value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" && !field.required ? null : trimmed;
}

/** "2026-10-09" is today or later; a revision may not start before today. */
export function effectiveFromProblem(value: string, today: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return "Choose the date it starts.";
  if (value < today) return "Today or later: calculations already made keep the old figures.";
  return null;
}
