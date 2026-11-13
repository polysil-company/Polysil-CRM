import type { BadgeVariant } from "@/components/ui/badge";
import type { Lead, LeadStage } from "@/features/leads/api/leads.schemas";
import type { ApplicationStatus } from "@/features/subsidy/api/subsidy-applications.schemas";
import { SYSTEM_TYPES, type SystemType } from "@/features/subsidy/api/subsidy.schemas";
import { formatFullDate, formatNumber } from "@/lib/format";

/** SUBS-004 … SUBS-006 · Words for an application's codes, and who may start one. */

export const APPLICATION_STATUS_LABELS: Readonly<Record<ApplicationStatus, string>> = {
  open: "Open",
  full_fp_received: "Fully paid",
  cancelled: "Cancelled",
};

export const APPLICATION_STATUS_DESCRIPTIONS: Readonly<Record<ApplicationStatus, string>> = {
  open: "Moving through the scheme's stages",
  full_fp_received: "Every payment received; closed by itself",
  cancelled: "Withdrawn; the lead can start again",
};

export const APPLICATION_STATUS_BADGE: Readonly<Record<ApplicationStatus, BadgeVariant>> = {
  open: "info",
  full_fp_received: "success",
  cancelled: "neutral",
};

/** "1 day", "12 days"; 0 is "0 days". */
export function formatDays(days: number): string {
  return days === 1 ? "1 day" : `${formatNumber(Math.max(0, days))} days`;
}

/** "Reached today", "12 days in this stage". */
export function daysInStageText(days: number): string {
  return days <= 0 ? "Reached today" : `${formatDays(days)} in this stage`;
}

/** The lead stages an application may start from. */
const FORWARDABLE: ReadonlySet<LeadStage> = new Set(["qualified", "quoted", "negotiation", "won"]);

/** The lead's system as a calculator system, or null when it has no subsidy calculation. */
export function subsidySystemOf(lead: Pick<Lead, "misSystem">): SystemType | null {
  return SYSTEM_TYPES.find((system) => system === lead.misSystem) ?? null;
}

/**
 * Why this lead can't start an application, in words, or null when it can. The rules are the
 * backend's (handover `subsidy-applications-contract.md`); it checks them again.
 */
export function cannotStartReason(lead: Pick<Lead, "type" | "stage" | "misSystem">): string | null {
  if (lead.type !== "subsidised") return "Only a subsidised enquiry can become an application.";
  if (!FORWARDABLE.has(lead.stage)) {
    return "The lead needs to be qualified, quoted, in negotiation or won first.";
  }
  if (subsidySystemOf(lead) === null) {
    return "Only drip, mini sprinkler and sprinkler have a subsidy calculation.";
  }
  return null;
}

/** A business date ("YYYY-MM-DD") as "14 Aug 2026", the same day in any browser's zone. */
export function formatBusinessDay(day: string): string {
  return formatFullDate(`${day}T12:00:00+05:30`);
}
