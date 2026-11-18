import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  masterRowsSchemas,
  quantityMatricesSchema,
  revisionResultSchema,
  unitCostMatricesSchema,
  type MasterKind,
  type MasterRows,
  type MatrixRequest,
  type QuantityMatrix,
  type RevisionRequest,
  type RevisionResult,
  type UnitCostMatrix,
} from "./subsidy-masters.schemas";

const log = createLogger({
  file: "features/subsidy/api/subsidy-masters.api.ts",
  dataId: "SUBS-012",
});

/** SUBS-012 · GET /subsidy-masters/{kind} — a scheme's rows in force on a date (today when null). */
export function listMaster<K extends MasterKind>(
  kind: K,
  scheme: string,
  on: string | null,
  signal?: AbortSignal,
): Promise<MasterRows[K]> {
  return apiRequest({
    dataId: "SUBS-012",
    logger: log,
    fn: "listMaster",
    path: `/subsidy-masters/${kind}`,
    query: { scheme, on: on ?? undefined },
    schema: masterRowsSchemas[kind],
    signal,
  });
}

/**
 * SUBS-012 · POST /subsidy-masters/{kind}/revisions — each row closes the row with its key in
 * force on that date and starts from it; rows not sent stay. 409 when one already starts that
 * day or later; 422 `revision_in_past` before today.
 */
export function reviseMaster<K extends MasterKind>({
  kind,
  body,
  idempotencyKey,
}: {
  kind: K;
  body: RevisionRequest<K>;
  idempotencyKey: string;
}): Promise<RevisionResult> {
  return apiRequest({
    dataId: "SUBS-012",
    logger: log,
    fn: "reviseMaster",
    method: "POST",
    path: `/subsidy-masters/${kind}/revisions`,
    body,
    idempotencyKey,
    schema: revisionResultSchema,
  });
}

/** SUBS-013 · GET /subsidy-masters/unit-cost-matrices/matrices — in force, with every cell. */
export function listUnitCostMatrices(
  scheme: string,
  on: string | null,
  signal?: AbortSignal,
): Promise<UnitCostMatrix[]> {
  return apiRequest({
    dataId: "SUBS-013",
    logger: log,
    fn: "listUnitCostMatrices",
    path: "/subsidy-masters/unit-cost-matrices/matrices",
    query: { scheme, on: on ?? undefined },
    schema: unitCostMatricesSchema,
    signal,
  });
}

/** SUBS-013 · GET /subsidy-masters/quantity-matrices/matrices — in force, with every cell. */
export function listQuantityMatrices(
  scheme: string,
  on: string | null,
  signal?: AbortSignal,
): Promise<QuantityMatrix[]> {
  return apiRequest({
    dataId: "SUBS-013",
    logger: log,
    fn: "listQuantityMatrices",
    path: "/subsidy-masters/quantity-matrices/matrices",
    query: { scheme, on: on ?? undefined },
    schema: quantityMatricesSchema,
    signal,
  });
}

/** SUBS-013 · POST /subsidy-masters/{kind}/matrices — the matrix in force ends that day. */
export function createMatrix({
  request,
  idempotencyKey,
}: {
  request: MatrixRequest;
  idempotencyKey: string;
}): Promise<RevisionResult> {
  return apiRequest({
    dataId: "SUBS-013",
    logger: log,
    fn: "createMatrix",
    method: "POST",
    path: `/subsidy-masters/${request.kind}/matrices`,
    body: request.body,
    idempotencyKey,
    schema: revisionResultSchema,
  });
}
