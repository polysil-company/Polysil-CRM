import type { BadgeVariant } from "@/components/ui/badge";
import type {
  ComplaintSeverity,
  ComplaintStatus,
} from "@/features/complaints/api/complaints.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

export const COMPLAINT_STATUS_LABELS: Readonly<Record<ComplaintStatus, string>> = {
  draft: "Draft",
  submitted: "Waiting for a check",
  under_qc: "With QC",
  qc_approved: "QC approved",
  qc_rejected: "QC rejected",
  remedy_pending: "Remedy under way",
  closed: "Closed",
  cancelled: "Cancelled",
};

/** One line under each status in the filter, for people new to the flow. */
export const COMPLAINT_STATUS_DESCRIPTIONS: Readonly<Record<ComplaintStatus, string>> = {
  draft: "Being written, or sent back by the manager to fix.",
  submitted: "Numbered; a manager checks it next.",
  under_qc: "The manager approved it; QC tests the sample.",
  qc_approved: "QC found a defect; a remedy is chosen next.",
  qc_rejected: "QC found no defect. Closed.",
  remedy_pending: "A refund or replacement is on its way.",
  closed: "Settled.",
  cancelled: "Withdrawn by whoever raised it.",
};

export const COMPLAINT_STATUS_BADGE: Readonly<Record<ComplaintStatus, BadgeVariant>> = {
  draft: "neutral",
  submitted: "info",
  under_qc: "primary",
  qc_approved: "success",
  qc_rejected: "danger",
  remedy_pending: "warning",
  closed: "outline",
  cancelled: "outline",
};

export const SEVERITY_LABELS: Readonly<Record<ComplaintSeverity, string>> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const SEVERITY_BADGE: Readonly<Record<ComplaintSeverity, BadgeVariant>> = {
  low: "neutral",
  medium: "warning",
  high: "danger",
};

/** The backend's field names for the complaint form's labels, for "fill these in" messages. */
const FIELD_NAMES: Readonly<Record<string, string>> = {
  dc_no: "the challan number",
  supply_date: "the supply date",
  lines: "the products",
};

/** How a refused complaint action reads, and whether the screen should just refresh. */
export interface ComplaintRefusal {
  readonly title: string;
  readonly message: string;
  /** Someone acted first: close and show the latest. */
  readonly stale: boolean;
  readonly fields: Readonly<Record<string, string>> | null;
}

/**
 * The backend's complaint refusals in plain words: `status_changed` and `complaint_not_draft`
 * (someone acted first), `missing_for_submit`, `nothing_defective`, `no_checker`,
 * `territory_without_state_code`, and a 403 (not this user's step).
 */
export function complaintRefusal(error: unknown): ComplaintRefusal {
  const fields = readFieldErrors(error);
  if (isApiError(error)) {
    switch (error.code) {
      case "status_changed":
      case "complaint_not_draft":
        return {
          title: "This complaint moved on",
          message: "Someone acted on it meanwhile. The page now shows where it stands.",
          stale: true,
          fields: null,
        };
      case "missing_for_submit": {
        const missing = Object.keys(fields ?? {}).map((field) => FIELD_NAMES[field] ?? field);
        return {
          title: "Not ready to submit",
          message: `Add ${missing.length === 0 ? "the missing details" : missing.join(" and ")} first: edit the draft.`,
          stale: false,
          fields,
        };
      }
      case "nothing_defective":
        return {
          title: "Nothing is marked defective",
          message: "Enter the defective quantity for at least one product, then submit.",
          stale: false,
          fields,
        };
      case "no_checker":
        return {
          title: "Nobody can check this complaint",
          message: "No manager covers its area yet. Ask the administrator to set one up.",
          stale: false,
          fields: null,
        };
      case "territory_without_state_code":
        return {
          title: "This place can't be numbered yet",
          message: "Its state has no code. Ask the administrator, or choose a nearby taluka.",
          stale: false,
          fields: { territory_id: "its state has no code yet" },
        };
      default:
        break;
    }
    if (error.status === 403) {
      return {
        title: "Not yours to do",
        message: "This step belongs to someone else on this complaint.",
        stale: false,
        fields: null,
      };
    }
  }
  const view = toUserFacingError(error);
  return { title: view.title, message: view.description, stale: false, fields };
}

/** One line of a complaint's history. */
export interface ComplaintHistoryEntry {
  readonly title: string;
  readonly detail: string | null;
  readonly tone: "neutral" | "info" | "success" | "warning" | "danger";
}

function textOf(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

/** Turns one history event into its line. A kind the screen doesn't know keeps a readable label. */
export function complaintHistoryEntry(
  kind: string,
  payload: Readonly<Record<string, unknown>>,
): ComplaintHistoryEntry {
  const remark = textOf(payload.remark);
  switch (kind) {
    case "complaint.created":
      return { title: "Raised as a draft", detail: null, tone: "neutral" };
    case "complaint.updated":
    case "complaint.lines_replaced":
      return { title: "Draft edited", detail: null, tone: "neutral" };
    case "complaint.submitted":
      return { title: "Submitted", detail: textOf(payload.complaint_no), tone: "info" };
    case "complaint.checked":
      return { title: "Approved by the manager, sent to QC", detail: remark, tone: "success" };
    case "complaint.returned":
      return { title: "Returned to fix", detail: remark, tone: "warning" };
    case "complaint.qc_approved":
      return { title: "QC approved: a defect", detail: remark, tone: "success" };
    case "complaint.qc_rejected":
      return { title: "QC rejected: no defect", detail: remark, tone: "danger" };
    case "complaint.cancelled":
      return { title: "Cancelled", detail: textOf(payload.reason), tone: "danger" };
    case "complaint.attachment_added":
      return { title: "File added", detail: textOf(payload.filename), tone: "neutral" };
    case "complaint.remedy_chosen":
      return { title: "Remedy chosen", detail: remark, tone: "info" };
    case "complaint.closed":
      return { title: "Closed", detail: remark, tone: "success" };
    default: {
      const words = kind.replace(/^complaint\./, "").replace(/_/g, " ");
      return {
        title: words.charAt(0).toUpperCase() + words.slice(1),
        detail: remark,
        tone: "neutral",
      };
    }
  }
}
