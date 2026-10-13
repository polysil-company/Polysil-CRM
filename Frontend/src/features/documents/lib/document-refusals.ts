import { DOCUMENTS_PER_RECORD } from "@/features/documents/api/documents.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

/**
 * DOC-002, DOC-003 · A document refusal in words (handover `documents-and-replacement-chain.md`).
 * `name` lands on the name box; everything else is said above the buttons.
 */
export interface DocumentRefusal {
  readonly message: string | null;
  readonly name: string | null;
  /** The record or the document is gone or closed: close the dialog and refresh. */
  readonly stale: boolean;
}

function sentence(text: string): string {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}${/[.!?]$/.test(text) ? "" : "."}`;
}

export function documentRefusal(error: unknown): DocumentRefusal {
  const none = { message: null, name: null, stale: false };
  if (!isApiError(error)) return { ...none, message: toUserFacingError(error).title };
  if (error.status === 413 || error.code === "attachment_too_large") {
    return { ...none, message: "Files up to 10 MB." };
  }
  switch (error.code) {
    case "attachment_type":
      return { ...none, message: "Only JPEG, PNG, WebP, HEIC or PDF files." };
    case "too_many_documents":
      return {
        ...none,
        message: `This record has ${String(DOCUMENTS_PER_RECORD)} documents. Remove one to add another.`,
      };
    case "record_closed":
      return {
        ...none,
        message: "This record takes no more documents: it was deleted, merged or voided.",
        stale: true,
      };
    case "storage_unavailable":
      return { ...none, message: "Files can't be stored right now. Try again in a few minutes." };
    default:
      break;
  }
  if (error.status === 403)
    return { ...none, message: "You may not change this record's documents." };
  if (error.status === 404) {
    return { ...none, message: "It's no longer there, or no longer yours to see.", stale: true };
  }
  const fields = readFieldErrors(error);
  if (fields !== null) {
    const { name, ...rest } = fields;
    const other = Object.values(rest)[0];
    return {
      ...none,
      name: name === undefined ? null : sentence(name),
      message: other === undefined ? null : sentence(other),
    };
  }
  return { ...none, message: toUserFacingError(error).title };
}
