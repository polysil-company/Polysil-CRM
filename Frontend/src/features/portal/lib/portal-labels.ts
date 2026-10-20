import type { BadgeVariant } from "@/components/ui/badge";
import { isApiError } from "@/lib/api/errors";

/** FARM-001 … FARM-003 · What the farmers' portal says, in plain words. */

interface StatusWords {
  readonly label: string;
  readonly tone: BadgeVariant;
}

const ENQUIRY: Readonly<Record<string, StatusWords>> = {
  in_progress: { label: "In progress", tone: "info" },
  won: { label: "Ordered", tone: "success" },
  closed: { label: "Closed", tone: "neutral" },
};

const QUOTATION: Readonly<Record<string, StatusWords>> = {
  sent: { label: "Sent to you", tone: "info" },
  accepted: { label: "Accepted", tone: "success" },
  closed: { label: "Closed", tone: "neutral" },
};

const ORDER: Readonly<Record<string, StatusWords>> = {
  in_progress: { label: "In progress", tone: "info" },
  being_revised: { label: "Being revised", tone: "warning" },
  dispatched: { label: "Dispatched", tone: "success" },
  closed: { label: "Completed", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "danger" },
};

const COMPLAINT: Readonly<Record<string, StatusWords>> = {
  in_progress: { label: "Being looked into", tone: "warning" },
  closed: { label: "Closed", tone: "neutral" },
};

function wordsFor(table: Readonly<Record<string, StatusWords>>, status: string): StatusWords {
  return table[status] ?? { label: status.replace(/_/g, " "), tone: "outline" };
}

export const enquiryStatus = (status: string): StatusWords => wordsFor(ENQUIRY, status);
export const quotationStatus = (status: string): StatusWords => wordsFor(QUOTATION, status);
export const orderStatus = (status: string): StatusWords => wordsFor(ORDER, status);
export const complaintStatus = (status: string): StatusWords => wordsFor(COMPLAINT, status);

/** "Drip", "Sprinkler": the system code as a word. */
export function systemText(system: string): string {
  const words = system.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The portal is switched off: the farmer can do nothing here until it is on again. */
export function isPortalOff(error: unknown): boolean {
  return isApiError(error) && error.status === 403 && error.code === "portal_off";
}

/** A refusal from `POST /portal/ratings` in words, or null when it is something else. */
export function portalRatingRefusal(error: unknown): string | null {
  if (!isApiError(error)) return null;
  switch (error.code) {
    case "not_rateable":
      return "This can't be rated yet.";
    case "rating_exists":
      return "This has been rated already.";
    case "not_found":
      return "We couldn't find this among your orders and complaints.";
    default:
      return null;
  }
}
