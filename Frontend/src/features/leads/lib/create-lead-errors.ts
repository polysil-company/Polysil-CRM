import type { CreateLeadFormField, CreateLeadRequest } from "@/features/leads/api/leads.schemas";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

/** Where each request field's 422 error lands on the New lead form. */
const FORM_FIELD_BY_REQUEST_FIELD: Readonly<Record<keyof CreateLeadRequest, CreateLeadFormField>> =
  {
    farmer_name: "customerName",
    mobile: "phone",
    email: "email",
    territory_id: "territory",
    village: "village",
    inquiry_type: "type",
    mis_system: "misSystem",
    source: "source",
    estimated_value: "estimatedValue",
    note: "note",
  };

/**
 * Territory refusals the backend explains with a code; its field message is written for
 * developers ("no org unit covers this territory"), so the form says it in plain words.
 */
const TERRITORY_MESSAGES_BY_CODE: Readonly<Record<string, string>> = {
  territory_without_org_unit:
    "No Polysil office covers this place yet. Choose the taluka or district around it.",
  territory_without_state_code:
    "This place isn't set up for new leads yet. Choose the taluka or district around it.",
};

function isRequestField(name: string): name is keyof CreateLeadRequest {
  return Object.hasOwn(FORM_FIELD_BY_REQUEST_FIELD, name);
}

/** "string should have at most 200 characters" → "String should have at most 200 characters." */
function toSentence(reason: string): string {
  const trimmed = reason.trim();
  if (trimmed === "") {
    return "Check this field.";
  }
  const capitalised = `${trimmed.charAt(0).toUpperCase()}${trimmed.slice(1)}`;
  return /[.!?]$/.test(capitalised) ? capitalised : `${capitalised}.`;
}

export interface CreateLeadFieldError {
  readonly field: CreateLeadFormField;
  readonly message: string;
}

/**
 * LEAD-002 · A 422 from POST /leads as errors on the form's fields. Paths can be nested
 * ("estimated_value.float"); the first segment names the field, and each field keeps its
 * first error. Paths the form has no field for are left out: when nothing maps, the caller
 * shows the general error instead.
 */
export function createLeadFieldErrors(error: unknown): CreateLeadFieldError[] {
  const fields = readFieldErrors(error);
  if (fields === null) {
    return [];
  }
  const territoryMessage =
    isApiError(error) && error.code ? TERRITORY_MESSAGES_BY_CODE[error.code] : undefined;

  const errors: CreateLeadFieldError[] = [];
  for (const [path, reason] of Object.entries(fields)) {
    const name = path.split(".")[0] ?? "";
    if (!isRequestField(name)) {
      continue;
    }
    const field = FORM_FIELD_BY_REQUEST_FIELD[name];
    if (errors.some((existing) => existing.field === field)) {
      continue;
    }
    const message =
      field === "territory" && territoryMessage ? territoryMessage : toSentence(reason);
    errors.push({ field, message });
  }
  return errors;
}
