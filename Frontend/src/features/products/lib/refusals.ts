import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

/** The backend's conflicts in words; anything else reads as the server put it. */
const CONFLICTS: Readonly<Record<string, string>> = {
  duplicate_description: "Another product already has this description.",
  hsn_same_start_date: "The heading in force starts that day: pick a later date.",
  tax_rate_same_start_date: "The rate in force starts that day: pick a later date.",
  price_list_published: "This list is published: its rates never change. Start a new list from it.",
  price_list_unpriced: "Some active products have no rate in this list.",
  price_list_overlap: "Another list of the same scope already covers these dates.",
};

function sentence(text: string): string {
  const trimmed = text.trim();
  return `${trimmed.charAt(0).toUpperCase()}${trimmed.slice(1)}${/[.!?]$/.test(trimmed) ? "" : "."}`;
}

/** A refusal split into what marks an input and what is said above the buttons. */
export function readRefusal(
  error: unknown,
  fieldNames: Readonly<Record<string, string>> = {},
): { fields: Record<string, string>; message: string | null } {
  const wire = readFieldErrors(error);
  if (wire !== null) {
    const fields: Record<string, string> = {};
    const rest: string[] = [];
    for (const [path, reason] of Object.entries(wire)) {
      const field = fieldNames[path];
      if (field === undefined) rest.push(`${path}: ${reason}`);
      else fields[field] = sentence(reason);
    }
    return { fields, message: rest.length === 0 ? null : sentence(rest.join("; ")) };
  }
  if (isApiError(error)) {
    if (error.status === 403) return { fields: {}, message: "You may not change this." };
    const known = error.code === undefined ? undefined : CONFLICTS[error.code];
    if (known !== undefined) {
      const field = error.code === "duplicate_description" ? fieldNames.description : undefined;
      return field === undefined
        ? { fields: {}, message: known }
        : { fields: { [field]: known }, message: null };
    }
  }
  return { fields: {}, message: toUserFacingError(error).title };
}
