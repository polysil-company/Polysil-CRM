import {
  CONSENT_VERSION_PATTERN,
  POLICY_BOUNDS,
  type Policy,
  type PolicyRequest,
} from "@/features/tracking/api/policy.schemas";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";

/** TRK-006 · The new-version form: its draft, its checks and the request it sends. */

/** ISO weekdays in order, Monday first, with their names. */
export const WEEKDAYS: readonly {
  readonly day: number;
  readonly name: string;
  readonly short: string;
}[] = [
  { day: 1, name: "Monday", short: "Mon" },
  { day: 2, name: "Tuesday", short: "Tue" },
  { day: 3, name: "Wednesday", short: "Wed" },
  { day: 4, name: "Thursday", short: "Thu" },
  { day: 5, name: "Friday", short: "Fri" },
  { day: 6, name: "Saturday", short: "Sat" },
  { day: 7, name: "Sunday", short: "Sun" },
];

export interface PolicyDraft {
  /** "2026-10-19T00:00", India time, as a datetime-local field holds it. */
  readonly effectiveFrom: string;
  readonly intervalSeconds: string;
  readonly distanceFilterM: string;
  readonly workStart: string;
  readonly workEnd: string;
  readonly workDays: readonly number[];
  readonly retentionDays: string;
  readonly visitPhotoRequired: boolean;
  readonly consentVersion: string;
  readonly consentText: string;
}

export type PolicyField =
  | "effectiveFrom"
  | "intervalSeconds"
  | "distanceFilterM"
  | "workStart"
  | "workEnd"
  | "workDays"
  | "retentionDays"
  | "consentVersion"
  | "consentText";

/** The form starts from the version in force, taking over at the start of tomorrow. */
export function draftOf(policy: Policy, today: string = todayInIndia()): PolicyDraft {
  return {
    effectiveFrom: `${shiftCalendarDay(today, 1)}T00:00`,
    intervalSeconds: String(policy.intervalSeconds),
    distanceFilterM: String(policy.distanceFilterM),
    workStart: policy.workStart,
    workEnd: policy.workEnd,
    workDays: policy.workDays,
    retentionDays: String(policy.retentionDays),
    visitPhotoRequired: policy.visitPhotoRequired,
    consentVersion: policy.consentVersion,
    consentText: policy.consentText,
  };
}

function wholeIn(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const number = Number(value.trim());
  return number >= min && number <= max ? number : null;
}

/** "2026-10-19T00:00" in India as an instant with its offset. */
export function indiaInstant(local: string): string {
  return `${local}:00+05:30`;
}

/** What is wrong with the draft, field by field, in words. `now` keeps it testable. */
export function policyProblems(
  draft: PolicyDraft,
  now: number = Date.now(),
): Partial<Record<PolicyField, string>> {
  const problems: Partial<Record<PolicyField, string>> = {};
  const starts = Date.parse(indiaInstant(draft.effectiveFrom));
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(draft.effectiveFrom) || Number.isNaN(starts)) {
    problems.effectiveFrom = "Choose when this version takes over.";
  } else if (starts < now) {
    problems.effectiveFrom = "Choose a time from now on: a version never starts in the past.";
  }
  const { intervalSeconds, distanceFilterM, retentionDays } = POLICY_BOUNDS;
  if (wholeIn(draft.intervalSeconds, intervalSeconds.min, intervalSeconds.max) === null) {
    problems.intervalSeconds = `A whole number of seconds from ${String(intervalSeconds.min)} to ${String(intervalSeconds.max)}.`;
  }
  if (wholeIn(draft.distanceFilterM, distanceFilterM.min, distanceFilterM.max) === null) {
    problems.distanceFilterM = `A whole number of metres from ${String(distanceFilterM.min)} to ${String(distanceFilterM.max)}.`;
  }
  if (wholeIn(draft.retentionDays, retentionDays.min, retentionDays.max) === null) {
    problems.retentionDays = `A whole number of days from ${String(retentionDays.min)} to ${String(retentionDays.max)}.`;
  }
  if (!/^\d{2}:\d{2}$/.test(draft.workStart)) problems.workStart = "Choose when the day starts.";
  if (!/^\d{2}:\d{2}$/.test(draft.workEnd)) {
    problems.workEnd = "Choose when the day ends.";
  } else if (draft.workEnd <= draft.workStart) {
    problems.workEnd = "The day ends after it starts.";
  }
  if (draft.workDays.length === 0) problems.workDays = "Choose at least one working day.";
  if (!CONSENT_VERSION_PATTERN.test(draft.consentVersion.trim())) {
    problems.consentVersion = "Letters, digits, dots, dashes or underscores, up to 20.";
  }
  if (draft.consentText.trim() === "") {
    problems.consentText = "Write the consent text staff will read.";
  } else if (draft.consentText.length > POLICY_BOUNDS.consentTextMax) {
    problems.consentText = "Up to 10,000 characters.";
  }
  return problems;
}

export function requestOf(draft: PolicyDraft): PolicyRequest {
  return {
    effective_from: indiaInstant(draft.effectiveFrom),
    interval_seconds: Number(draft.intervalSeconds.trim()),
    distance_filter_m: Number(draft.distanceFilterM.trim()),
    work_start: draft.workStart,
    work_end: draft.workEnd,
    work_days: [...draft.workDays].sort((left, right) => left - right),
    retention_days: Number(draft.retentionDays.trim()),
    visit_photo_required: draft.visitPhotoRequired,
    consent_version: draft.consentVersion.trim(),
    consent_text: draft.consentText.trim(),
  };
}

/** The backend's field names onto the form's. */
export const POLICY_WIRE_FIELDS: Readonly<Record<string, PolicyField>> = {
  effective_from: "effectiveFrom",
  interval_seconds: "intervalSeconds",
  distance_filter_m: "distanceFilterM",
  work_start: "workStart",
  work_end: "workEnd",
  work_days: "workDays",
  retention_days: "retentionDays",
  consent_version: "consentVersion",
  consent_text: "consentText",
};

/** "Monday to Saturday", "Monday, Wednesday and Friday", "Every day". */
export function workDaysText(days: readonly number[]): string {
  const sorted = [...days].sort((left, right) => left - right);
  if (sorted.length === 7) return "Every day";
  const names = sorted.map((day) => WEEKDAYS.find((item) => item.day === day)?.name ?? String(day));
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const contiguous =
    first !== undefined &&
    last !== undefined &&
    sorted.length > 2 &&
    last - first === sorted.length - 1;
  if (contiguous) return `${names[0] ?? ""} to ${names[names.length - 1] ?? ""}`;
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1] ?? ""}`;
}
