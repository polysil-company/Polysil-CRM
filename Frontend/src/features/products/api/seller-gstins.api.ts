import { z } from "zod";

import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  lutSchema,
  sellerGstinsSchema,
  type AddLutRequest,
  type Lut,
  type SellerGstin,
} from "./seller-gstins.schemas";

const log = createLogger({
  file: "features/products/api/seller-gstins.api.ts",
  dataId: "MSTR-018",
});

function lutsPath(gstinId: string): `/${string}` {
  return `/seller-gstins/${encodeURIComponent(gstinId)}/luts`;
}

/** MSTR-018 · Our registrations, the default first, each with its LUTs (products.view). */
export function listSellerGstins(signal?: AbortSignal): Promise<SellerGstin[]> {
  return apiRequest({
    dataId: "MSTR-018",
    logger: log,
    fn: "listSellerGstins",
    path: "/seller-gstins",
    schema: sellerGstinsSchema,
    signal,
  });
}

/**
 * MSTR-018 · Record a LUT for one financial year (products.edit). 409 `lut_overlap` or
 * `lut_duplicate`; 422 `lut_dates` when the range crosses 31 March or ends before it starts.
 */
export function addLut({
  gstinId,
  body,
  idempotencyKey,
}: {
  readonly gstinId: string;
  readonly body: AddLutRequest;
  readonly idempotencyKey: string;
}): Promise<Lut> {
  return apiRequest({
    dataId: "MSTR-018",
    logger: log,
    fn: "addLut",
    method: "POST",
    path: lutsPath(gstinId),
    body,
    idempotencyKey,
    schema: lutSchema,
  });
}

/** MSTR-018 · Remove a LUT no document carries yet (products.edit). 409 `lut_in_use`. */
export function deleteLut({
  gstinId,
  lutId,
  idempotencyKey,
}: {
  readonly gstinId: string;
  readonly lutId: string;
  readonly idempotencyKey: string;
}): Promise<void> {
  return apiRequest({
    dataId: "MSTR-018",
    logger: log,
    fn: "deleteLut",
    method: "DELETE",
    path: `${lutsPath(gstinId)}/${encodeURIComponent(lutId)}`,
    idempotencyKey,
    schema: z.undefined(),
  });
}
