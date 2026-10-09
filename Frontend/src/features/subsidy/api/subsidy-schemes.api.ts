import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  schemeDetailSchema,
  schemeListSchema,
  stageRenamedSchema,
  type CreateSchemeRequest,
  type PatchSchemeRequest,
  type SchemeDetail,
  type SchemeRow,
} from "./subsidy-schemes.schemas";

const log = createLogger({
  file: "features/subsidy/api/subsidy-schemes.api.ts",
  dataId: "SUBS-014",
});

function schemePath(code: string, rest = ""): `/${string}` {
  return `/subsidy-schemes/${encodeURIComponent(code)}${rest}`;
}

/** SUBS-014 · GET /subsidy-schemes — every scheme, with its state and whether it's ready. */
export function listSchemes(signal?: AbortSignal): Promise<SchemeRow[]> {
  return apiRequest({
    dataId: "SUBS-014",
    logger: log,
    fn: "listSchemes",
    path: "/subsidy-schemes",
    schema: schemeListSchema,
    signal,
  });
}

/** SUBS-014 · GET /subsidy-schemes/{code} — the readiness panel, on a date (today when null). */
export function getScheme(
  code: string,
  on: string | null,
  signal?: AbortSignal,
): Promise<SchemeDetail> {
  return apiRequest({
    dataId: "SUBS-014",
    logger: log,
    fn: "getScheme",
    path: schemePath(code),
    query: { on: on ?? undefined },
    schema: schemeDetailSchema,
    signal,
  });
}

/**
 * SUBS-014 · POST /subsidy-schemes — another state's scheme, copying a template's engine
 * settings and stages, never its figures. 409 `code_taken`, `state_has_scheme`,
 * `unlinked_scheme_exists`.
 */
export function createScheme({
  body,
  idempotencyKey,
}: {
  body: CreateSchemeRequest;
  idempotencyKey: string;
}): Promise<SchemeDetail> {
  return apiRequest({
    dataId: "SUBS-014",
    logger: log,
    fn: "createScheme",
    method: "POST",
    path: "/subsidy-schemes",
    body,
    idempotencyKey,
    schema: schemeDetailSchema,
  });
}

/** SUBS-014 · PATCH /subsidy-schemes/{code} — rename, switch off or on, or link to its state. */
export function patchScheme({
  code,
  body,
  idempotencyKey,
}: {
  code: string;
  body: PatchSchemeRequest;
  idempotencyKey: string;
}): Promise<SchemeDetail> {
  return apiRequest({
    dataId: "SUBS-014",
    logger: log,
    fn: "patchScheme",
    method: "PATCH",
    path: schemePath(code),
    body,
    idempotencyKey,
    schema: schemeDetailSchema,
  });
}

/** SUBS-014 · PATCH /subsidy-schemes/{code}/stages/{stageCode} — a stage's name. */
export async function renameStage({
  code,
  stageCode,
  name,
  idempotencyKey,
}: {
  code: string;
  stageCode: string;
  name: string;
  idempotencyKey: string;
}): Promise<void> {
  await apiRequest({
    dataId: "SUBS-014",
    logger: log,
    fn: "renameStage",
    method: "PATCH",
    path: schemePath(code, `/stages/${encodeURIComponent(stageCode)}`),
    body: { name },
    idempotencyKey,
    schema: stageRenamedSchema,
  });
}
