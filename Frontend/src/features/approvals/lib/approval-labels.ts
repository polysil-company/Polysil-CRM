import { z } from "zod";

import type { ApprovalDocType } from "@/features/approvals/api/approvals.schemas";
import { roleLabel } from "@/features/quotations/lib/quotation-lifecycle";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";

/** APPR-001 · Words for the inbox. */

export const DOC_TYPE_LABELS: Readonly<Record<ApprovalDocType, string>> = {
  quotation: "Quotation discount",
  sales_order: "Sales order",
  complaint: "Complaint refund",
};

/** "Draft quotation" for a quotation that has no number yet, else its number. */
export function documentTitle(docType: ApprovalDocType, number: string | null): string {
  if (number !== null) {
    return number;
  }
  return docType === "quotation" ? "Draft quotation" : DOC_TYPE_LABELS[docType];
}

/**
 * The backend asks for a remark to reject, and on every Accounts decision: Accounts checks
 * payment outside the system, and the remark is the record (role `account_manager`,
 * backend migration 013, BE-018). This says what a required remark is for when it is left
 * empty, and is null when the remark is optional.
 */
export function missingRemarkMessage(
  decision: "approve" | "reject",
  role: string,
  docType: ApprovalDocType = "sales_order",
): string | null {
  if (decision === "reject") {
    return "Say why. The person who asked reads it.";
  }
  if (role !== "account_manager") return null;
  // A refund's last step is the payout: its remark is the payment reference (CMPL-007).
  return docType === "complaint"
    ? "Enter the payment reference: the UTR or cheque number."
    : "Note the payment check: what was received or agreed.";
}

/** "State Manager's step": whose step a row is, for a manager covering a lower one. */
export function stepOwnerLabel(role: string): string {
  return `${roleLabel(role)}'s step`;
}

const fieldsSchema = z.object({ fields: z.record(z.string(), z.string()).optional() });

export interface DecisionRefusal {
  readonly title: string;
  readonly message: string;
  /** The row is out of date: close the dialog and show the latest inbox. */
  readonly stale: boolean;
  /** A field error on the remark, to show on the field. */
  readonly remark: string | null;
}

/** Why the backend refused a decision, in words the manager can act on. */
export function decisionRefusal(error: unknown): DecisionRefusal {
  if (!isApiError(error)) {
    const view = toUserFacingError(error);
    return { title: view.title, message: view.description, stale: false, remark: null };
  }
  const fields = fieldsSchema.safeParse(error.details).data?.fields ?? {};
  switch (error.code) {
    case "step_already_decided":
      return {
        title: "Already decided",
        message: "Someone decided this step while you had it open. The inbox now shows the latest.",
        stale: true,
        remark: null,
      };
    case "request_closed":
      return {
        title: "The request was withdrawn",
        message: "The document was changed or cancelled after it was sent for approval.",
        stale: true,
        remark: null,
      };
    case "figures_changed":
      return {
        title: "The figures changed",
        message:
          "The draft was edited after the request, so the request was withdrawn. The officer asks again for the new figures.",
        stale: true,
        remark: null,
      };
    case "earlier_step_undecided":
      return {
        title: "Not your turn yet",
        message: "An earlier step is still waiting. It comes to you once that one is decided.",
        stale: true,
        remark: null,
      };
    case "not_your_step":
      return {
        title: "This step isn't yours",
        message: "It waits on another role. Refresh the inbox to see what is yours.",
        stale: true,
        remark: null,
      };
    case "self_approval":
      return {
        title: "You raised this one",
        message: "Someone else must decide a request you raised.",
        stale: false,
        remark: null,
      };
    default: {
      if (fields.remark !== undefined) {
        return {
          title: "Add a remark",
          message: "A return needs its reason, and an Accounts decision its payment check.",
          stale: false,
          remark: "Add a remark",
        };
      }
      const view = toUserFacingError(error);
      return { title: view.title, message: view.description, stale: false, remark: null };
    }
  }
}

/** APPR-002 · Who a limit row is for, as the business says it. */
export function limitRoleLabel(role: string): string {
  switch (role) {
    case "field_officer":
      return "Field officer";
    case "admin_sales":
      return "Admin-Sales";
    default:
      return roleLabel(role);
  }
}
