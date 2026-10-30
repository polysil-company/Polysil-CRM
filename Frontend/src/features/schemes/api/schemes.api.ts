import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  entitlementPageSchema,
  schemePageSchema,
  schemeSchema,
  standingSchema,
  type EntitlementListParams,
  type EntitlementPage,
  type Scheme,
  type SchemeCreateRequest,
  type SchemeListParams,
  type SchemePage,
  type SchemePatchRequest,
  type Standing,
} from "./schemes.schemas";

const log = createLogger({ file: "features/schemes/api/schemes.api.ts", dataId: "SCHM-001" });

/** SCHM-001 · GET /schemes: newest first, a page at a time. */
export function listSchemes(
  params: SchemeListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<SchemePage> {
  return apiRequest({
    dataId: "SCHM-001",
    logger: log,
    fn: "listSchemes",
    path: "/schemes",
    query: {
      status: params.status ?? undefined,
      scheme_type: params.type ?? undefined,
      q: params.q === "" ? undefined : params.q,
      cursor: params.cursor ?? undefined,
    },
    schema: schemePageSchema,
    signal,
  });
}

/** SCHM-001 · GET /schemes/{id} */
export function getScheme(schemeId: string, signal?: AbortSignal): Promise<Scheme> {
  return apiRequest({
    dataId: "SCHM-001",
    logger: log,
    fn: "getScheme",
    path: `/schemes/${schemeId}`,
    schema: schemeSchema,
    signal,
  });
}

/** SCHM-002 · POST /schemes */
export function createScheme({
  body,
  idempotencyKey,
}: {
  body: SchemeCreateRequest;
  idempotencyKey: string;
}): Promise<Scheme> {
  return apiRequest({
    dataId: "SCHM-002",
    logger: log,
    fn: "createScheme",
    method: "POST",
    path: "/schemes",
    body,
    idempotencyKey,
    schema: schemeSchema,
  });
}

/** SCHM-002 · PATCH /schemes/{id}: only what changes; `targets`, if sent, replaces the list. */
export function patchScheme({
  schemeId,
  body,
  idempotencyKey,
}: {
  schemeId: string;
  body: SchemePatchRequest;
  idempotencyKey: string;
}): Promise<Scheme> {
  return apiRequest({
    dataId: "SCHM-002",
    logger: log,
    fn: "patchScheme",
    method: "PATCH",
    path: `/schemes/${schemeId}`,
    body,
    idempotencyKey,
    schema: schemeSchema,
  });
}

/** SCHM-003 · GET /schemes/{id}/standing: staff name the partner; a partner user gets its own. */
export function getStanding(
  schemeId: string,
  partnerId: string | null,
  signal?: AbortSignal,
): Promise<Standing> {
  return apiRequest({
    dataId: "SCHM-003",
    logger: log,
    fn: "getStanding",
    path: `/schemes/${schemeId}/standing`,
    query: { partner_id: partnerId ?? undefined },
    schema: standingSchema,
    signal,
  });
}

/** SCHM-004 · GET /scheme-entitlements: credits, newest first. */
export function listEntitlements(
  params: EntitlementListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<EntitlementPage> {
  return apiRequest({
    dataId: "SCHM-004",
    logger: log,
    fn: "listEntitlements",
    path: "/scheme-entitlements",
    query: {
      status: params.status ?? undefined,
      partner_id: params.partnerId ?? undefined,
      cursor: params.cursor ?? undefined,
    },
    schema: entitlementPageSchema,
    signal,
  });
}
