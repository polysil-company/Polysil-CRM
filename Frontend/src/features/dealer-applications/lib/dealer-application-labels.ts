import type { BadgeVariant } from "@/components/ui/badge";
import type {
  DealerApplicationStatus,
  Decision,
  FirmType,
} from "@/features/dealer-applications/api/dealer-applications.schemas";

/** CHNL-007 · Words for a dealer application's status. */
export const DEALER_APPLICATION_STATUS_LABELS: Readonly<Record<DealerApplicationStatus, string>> = {
  draft: "With the applicant",
  submitted: "Submitted",
  returned: "Returned to the applicant",
  approved: "Approved",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const FIRM_TYPE_LABELS: Readonly<Record<FirmType, string>> = {
  proprietorship: "Proprietorship",
  partnership: "Partnership",
  llp: "LLP",
  company: "Company",
};

export const DECISION_LABELS: Readonly<Record<Decision, string>> = {
  approve: "Approve",
  return: "Return to the applicant",
  reject: "Reject",
};

/** What `missing` names: a field or a document type (the backend's `dealer_application_missing`). */
const MISSING_LABELS: Readonly<Record<string, string>> = {
  firm_type: "Firm type",
  gstin: "GSTIN",
  pan: "PAN",
  address: "Address",
  pincode: "Pincode",
  bank_account_name: "Bank account name",
  bank_account_no: "Bank account number",
  bank_ifsc: "IFSC",
  gst_certificate: "GST certificate (document)",
  pan_card: "PAN card (document)",
  cancelled_cheque: "Cancelled cheque (document)",
};

export function missingLabel(key: string): string {
  return MISSING_LABELS[key] ?? key.replaceAll("_", " ");
}

export const DEALER_APPLICATION_STATUS_BADGE: Readonly<
  Record<DealerApplicationStatus, BadgeVariant>
> = {
  draft: "neutral",
  submitted: "info",
  returned: "warning",
  approved: "success",
  rejected: "danger",
  withdrawn: "neutral",
};

/** CHNL-008 · The documents an applicant uploads. */
export const APPLICANT_DOCUMENT_LABELS: Readonly<Record<string, string>> = {
  gst_certificate: "GST certificate",
  pan_card: "PAN card",
  cancelled_cheque: "Cancelled cheque",
  shop_photo: "Shop photo",
  shop_licence: "Shop licence",
  other: "Other",
};
