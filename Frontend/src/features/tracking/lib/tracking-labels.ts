import type { MapTone } from "@/components/patterns/map-view";
import type { BadgeVariant } from "@/components/ui/badge";
import type { TeamMemberState, VisitOutcome } from "@/features/tracking/api/tracking.schemas";
import { formatNumber } from "@/lib/format";

/** TRK-001, TRK-002 · What field tracking says on screen. */

export const MEMBER_STATE: Readonly<
  Record<TeamMemberState, { label: string; badge: BadgeVariant; tone: MapTone }>
> = {
  on_duty: { label: "On duty", badge: "success", tone: "success" },
  stale: { label: "Not heard from", badge: "warning", tone: "muted" },
  off_duty: { label: "Off duty", badge: "neutral", tone: "muted" },
};

export const VISIT_OUTCOME_LABELS: Readonly<Record<VisitOutcome, string>> = {
  met: "Met",
  not_available: "Not available",
  follow_up: "Follow up",
  other: "Other",
};

const END_REASONS: Readonly<Record<string, string>> = {
  user: "ended by them",
  auto: "ended after hours",
  consent_withdrawn: "ended when consent was withdrawn",
  deactivated: "ended when the account was switched off",
};

export function dutyEndText(reason: string | null): string {
  return reason === null ? "" : (END_REASONS[reason] ?? reason.replace(/_/g, " "));
}

/** "1 h 20 min", "45 min". */
export function minutesText(minutes: number): string {
  if (minutes < 60) return `${formatNumber(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0
    ? `${formatNumber(hours)} h`
    : `${formatNumber(hours)} h ${formatNumber(rest)} min`;
}

/** A role code in words: "field_officer" → "Field officer". */
export function roleText(role: string | null): string {
  if (role === null) return "";
  const words = role.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Below this the battery is worth a warning: tracking stops when the phone dies. */
export const LOW_BATTERY_PCT = 20;
