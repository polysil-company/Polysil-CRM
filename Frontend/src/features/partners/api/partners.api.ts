import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import type { ApiPath } from "@/lib/api/url";
import { createLogger } from "@/lib/logger";

import {
  gstinLookupSchema,
  partnerPageSchema,
  partnerSchema,
  partnerStateSchema,
  type CreatePartnerRequest,
  type GstinLookup,
  type Partner,
  type PartnerListParams,
  type PartnerPage,
  type PartnerStateChange,
  type PartnerType,
  type PatchPartnerRequest,
} from "./partners.schemas";

const log = createLogger({ file: "features/partners/api/partners.api.ts", dataId: "CHNL-001" });

export const PARTNER_PAGE_SIZE = 25;
/** How many parents one search in the parent picker returns. */
const PARENT_SEARCH_LIMIT = 20;

function partnerPath(partnerId: string, rest = ""): ApiPath {
  return `/partners/${encodeURIComponent(partnerId)}${rest}`;
}

function filterQuery(params: PartnerListParams): Record<string, string | boolean | undefined> {
  return {
    q: params.q.trim() === "" ? undefined : params.q.trim(),
    partner_type: params.type ?? undefined,
    parent_id: params.parentId ?? undefined,
    is_active: params.active ?? undefined,
  };
}

function logSkipped(fn: string, skipped: number, kept: number): void {
  if (skipped > 0) {
    log.warn(fn, `left out ${String(skipped)} row(s) that did not match the contract`, {
      dataId: "CHNL-001",
      context: { skipped, kept },
    });
  }
}

/** CHNL-001 · GET /partners — the partners in scope, newest first, filtered. */
export async function listPartners(
  params: PartnerListParams,
  signal?: AbortSignal,
): Promise<PartnerPage> {
  const page = await apiRequest({
    dataId: "CHNL-001",
    logger: log,
    fn: "listPartners",
    path: "/partners",
    query: {
      ...filterQuery(params),
      cursor: params.cursor ?? undefined,
      limit: PARTNER_PAGE_SIZE,
      include_total: params.cursor === null,
    },
    schema: partnerPageSchema,
    signal,
  });
  logSkipped("listPartners", page.skipped, page.items.length);
  return page;
}

/**
 * CHNL-002 · The open partners of one type matching what was typed: the parent a new dealer
 * or sub-dealer goes under.
 */
export async function searchParents(
  type: PartnerType,
  q: string,
  signal?: AbortSignal,
): Promise<readonly Partner[]> {
  const page = await apiRequest({
    dataId: "CHNL-002",
    logger: log,
    fn: "searchParents",
    path: "/partners",
    query: {
      q: q.trim() === "" ? undefined : q.trim(),
      partner_type: type,
      is_active: true,
      limit: PARENT_SEARCH_LIMIT,
    },
    schema: partnerPageSchema,
    signal,
  });
  logSkipped("searchParents", page.skipped, page.items.length);
  return page.items;
}

/**
 * CHNL-001 · GET /partners/export — the list as an Excel file, with the same filters: every
 * page, nothing outside the caller's scope. More than 5,000 rows is `422 export_too_large`.
 */
export function exportPartners(params: PartnerListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "CHNL-001",
    logger: log,
    fn: "exportPartners",
    path: "/partners/export",
    query: filterQuery(params),
  });
}

/** CHNL-001 · GET /partners/{id} */
export function getPartner(partnerId: string, signal?: AbortSignal): Promise<Partner> {
  return apiRequest({
    dataId: "CHNL-001",
    logger: log,
    fn: "getPartner",
    path: partnerPath(partnerId),
    schema: partnerSchema,
    signal,
  });
}

/** CHNL-006 · GET /gstin/{gstin}: the GST record's names. Its PAN and address stay out of logs. */
export function lookupGstin(gstin: string, signal?: AbortSignal): Promise<GstinLookup> {
  return apiRequest({
    dataId: "CHNL-006",
    logger: log,
    fn: "lookupGstin",
    path: `/gstin/${encodeURIComponent(gstin)}`,
    schema: gstinLookupSchema,
    sensitive: true,
    signal,
  });
}

/** CHNL-002 · POST /partners. Tax numbers and contacts are in the body: logged without it. */
export function createPartner({
  body,
  idempotencyKey,
}: {
  body: CreatePartnerRequest;
  idempotencyKey: string;
}): Promise<Partner> {
  return apiRequest({
    dataId: "CHNL-002",
    logger: log,
    fn: "createPartner",
    method: "POST",
    path: "/partners",
    body,
    idempotencyKey,
    schema: partnerSchema,
    sensitive: true,
  });
}

/** CHNL-003 · PATCH /partners/{id} — only what changes. */
export function patchPartner({
  partnerId,
  body,
  idempotencyKey,
}: {
  partnerId: string;
  body: PatchPartnerRequest;
  idempotencyKey: string;
}): Promise<Partner> {
  return apiRequest({
    dataId: "CHNL-003",
    logger: log,
    fn: "patchPartner",
    method: "PATCH",
    path: partnerPath(partnerId),
    body,
    idempotencyKey,
    schema: partnerSchema,
    sensitive: true,
  });
}

/**
 * CHNL-004 · POST /partners/{id}/close or /reopen. Closing signs out and deactivates every
 * user anchored on the partner; reopening restores the partner only.
 */
export function setPartnerOpen({
  partnerId,
  open,
  idempotencyKey,
}: {
  partnerId: string;
  open: boolean;
  idempotencyKey: string;
}): Promise<PartnerStateChange> {
  return apiRequest({
    dataId: "CHNL-004",
    logger: log,
    fn: open ? "reopenPartner" : "closePartner",
    method: "POST",
    path: partnerPath(partnerId, open ? "/reopen" : "/close"),
    idempotencyKey,
    schema: partnerStateSchema,
  });
}
