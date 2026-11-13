import type {
  StageDef,
  StageEntry,
  StageField,
} from "@/features/subsidy/api/subsidy-applications.schemas";

/**
 * SUBS-006 · The "Record stage" form's logic, kept apart from the dialog. Every value is a
 * string; a field emptied sends null, which clears it on the backend — so only what changed
 * from the latest value is sent, and a field left alone is never cleared by accident.
 */

/** The latest value of each field across the history: the backend's rule too. */
export function latestValues(entries: readonly StageEntry[]): Readonly<Record<string, string>> {
  const values: Record<string, string> = {};
  for (const entry of entries) {
    for (const [key, value] of Object.entries(entry.values)) {
      if (value === null) delete values[key];
      else values[key] = value;
    }
  }
  return values;
}

/** The form's starting values for a stage: what each of its fields holds now. */
export function initialValues(
  stage: StageDef,
  latest: Readonly<Record<string, string>>,
): Record<string, string> {
  return Object.fromEntries(stage.fields.map((field) => [field.key, latest[field.key] ?? ""]));
}

/** What the request sends: the fields that changed, an emptied one as null. */
export function changedValues(
  stage: StageDef,
  values: Readonly<Record<string, string>>,
  latest: Readonly<Record<string, string>>,
): Record<string, string | null> {
  const changed: Record<string, string | null> = {};
  for (const field of stage.fields) {
    const now = (values[field.key] ?? "").trim();
    const before = latest[field.key] ?? "";
    if (now !== before) changed[field.key] = now === "" ? null : now;
  }
  return changed;
}

/** A field's mistake as typed, before the backend sees it; null when it reads right. */
export function fieldProblem(field: StageField, value: string, today: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return field.required ? `Enter the ${field.label}.` : null;
  if (field.type === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return "Enter a date.";
    if (trimmed > today) return "Not after today.";
  }
  if (field.type === "amount") {
    if (!/^\d+(\.\d+)?$/.test(trimmed)) return "Enter an amount in rupees, like 1250.50.";
    if ((trimmed.split(".")[1]?.length ?? 0) > 2) return "At most two decimals (paise).";
    if (Number(trimmed) >= 1e12) return "That amount is too large.";
  }
  if (field.type === "text" && trimmed.length > 500) return "Up to 500 characters.";
  return null;
}

/** Going back, or recording the current stage again, needs a remark. */
export function needsRemark(stage: StageDef, currentSeq: number): boolean {
  return stage.seq <= currentSeq;
}
