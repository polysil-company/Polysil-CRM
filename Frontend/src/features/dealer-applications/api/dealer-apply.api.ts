import { z } from "zod";

import { gstinLookupSchema, type GstinLookup } from "@/features/partners/api/partners.schemas";
import { apiRequest } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import type { DealerApplicationFieldsRequest } from "./dealer-applications.schemas";
import {
  applicantSessionSchema,
  applicantViewSchema,
  codeSentSchema,
  submittedSchema,
  uploadedSchema,
  type ApplicantDocumentType,
  type ApplicantView,
} from "./dealer-apply.schemas";

const log = createLogger({
  file: "features/dealer-applications/api/dealer-apply.api.ts",
  dataId: "CHNL-008",
});

/**
 * CHNL-008 · The applicant's calls: public (`auth: "none"`), the link's token in the path,
 * and once verified the applicant's session as `X-Apply-Session`. Every body is sensitive:
 * tax, bank and contact details, codes and the session stay out of the logs.
 */
function applyPath(token: string, rest = ""): ApiPath {
  return `/public/dealer-apply/${encodeURIComponent(token)}${rest}`;
}

interface Applicant {
  readonly token: string;
  /** Null before the mobile is verified. */
  readonly session: string | null;
}

/** GET …/{token}: the firm, the masked mobile and what is needed; every field once verified. */
export function getApplicantView(
  { token, session }: Applicant,
  signal?: AbortSignal,
): Promise<ApplicantView> {
  return apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "getApplicantView",
    path: applyPath(token),
    auth: "none",
    applicantSession: session,
    schema: applicantViewSchema,
    sensitive: true,
    signal,
  });
}

/** POST …/verify: a WhatsApp code to the application's mobile. One a minute, ten a day. */
export async function sendApplicantCode(token: string): Promise<void> {
  await apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "sendApplicantCode",
    method: "POST",
    path: applyPath(token, "/verify"),
    auth: "none",
    schema: codeSentSchema,
  });
}

/** POST …/verify/check: the session for 2 hours. A wrong code is `422 invalid_code`. */
export function checkApplicantCode(token: string, code: string): Promise<string> {
  return apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "checkApplicantCode",
    method: "POST",
    path: applyPath(token, "/verify/check"),
    auth: "none",
    body: { code },
    schema: applicantSessionSchema,
    sensitive: true,
  });
}

/** PATCH …/{token}: save fields while draft or returned; answers the view again. */
export function patchApplicantFields(
  applicant: Applicant,
  body: DealerApplicationFieldsRequest,
): Promise<ApplicantView> {
  return apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "patchApplicantFields",
    method: "PATCH",
    path: applyPath(applicant.token),
    auth: "none",
    applicantSession: applicant.session,
    body,
    schema: applicantViewSchema,
    sensitive: true,
  });
}

/** GET …/gstin/{gstin}: the GSTIN read from itself, for "Check GSTIN". */
export function checkApplicantGstin(
  applicant: Applicant,
  gstin: string,
  signal?: AbortSignal,
): Promise<GstinLookup> {
  return apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "checkApplicantGstin",
    path: applyPath(applicant.token, `/gstin/${encodeURIComponent(gstin)}`),
    auth: "none",
    applicantSession: applicant.session,
    schema: gstinLookupSchema,
    sensitive: true,
    signal,
  });
}

/** POST …/documents (multipart): JPEG, PNG, WebP, HEIC or PDF up to 10 MB; "other" needs a name. */
export function uploadApplicantDocument(
  applicant: Applicant,
  input: { docType: ApplicantDocumentType; name: string | null; file: File },
): Promise<{ id: string; created: boolean }> {
  const form = new FormData();
  form.set("doc_type", input.docType);
  if (input.name !== null) form.set("name", input.name);
  form.set("file", input.file);
  return apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "uploadApplicantDocument",
    method: "POST",
    path: applyPath(applicant.token, "/documents"),
    auth: "none",
    applicantSession: applicant.session,
    body: form,
    schema: uploadedSchema,
    timeoutMs: 60_000,
  });
}

/** DELETE …/documents/{id}: one of the applicant's own uploads. */
export async function removeApplicantDocument(
  applicant: Applicant,
  documentId: string,
): Promise<void> {
  await apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "removeApplicantDocument",
    method: "DELETE",
    path: applyPath(applicant.token, `/documents/${encodeURIComponent(documentId)}`),
    auth: "none",
    applicantSession: applicant.session,
    schema: z.undefined(),
  });
}

/** POST …/submit. `422 application_incomplete` names what is missing. */
export async function submitApplicantApplication(applicant: Applicant): Promise<void> {
  await apiRequest({
    dataId: "CHNL-008",
    logger: log,
    fn: "submitApplicantApplication",
    method: "POST",
    path: applyPath(applicant.token, "/submit"),
    auth: "none",
    applicantSession: applicant.session,
    schema: submittedSchema,
  });
}
