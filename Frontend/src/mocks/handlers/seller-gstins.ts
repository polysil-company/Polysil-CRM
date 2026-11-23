import { http, HttpResponse } from "msw";
import { z } from "zod";

import { ARN_PATTERN, type LutWire } from "@/features/products/api/seller-gstins.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockUuid } from "@/mocks/data/reference";
import { SELLER_GSTIN_SPACE } from "@/mocks/data/seller-gstins";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * MSTR-018 · Seller GSTINs and their LUTs (`docs/api/seller-gstins.md`): products.view reads,
 * products.edit adds and removes a LUT. A LUT covers one financial year, 1 April to 31 March.
 */

function allowed(action: "view" | "edit"): boolean {
  return can(mockPermissionsFor(readMockRole()), "products", action);
}

const lutBody = z.object({
  arn: z.string().trim().regex(ARN_PATTERN, "10 to 20 letters and digits."),
  valid_from: z.iso.date("A date."),
  valid_to: z.iso.date("A date."),
});

/** The financial year a day falls in, by its starting year: 2026-05-01 → 2026. */
function financialYear(day: string): number {
  const year = Number(day.slice(0, 4));
  return Number(day.slice(5, 7)) >= 4 ? year : year - 1;
}

function overlaps(left: LutWire, from: string, to: string): boolean {
  return left.valid_from <= to && from <= left.valid_to;
}

let issued = 0;

export const sellerGstinHandlers = [
  http.get(buildApiUrl("/seller-gstins"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return errorResponse(403, "forbidden", "Needs products.view.");
    return HttpResponse.json({ data: mockDb.sellerGstins });
  }),

  http.post(buildApiUrl("/seller-gstins/:gstinId/luts"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return errorResponse(403, "forbidden", "Needs products.edit.");
    const registration = mockDb.sellerGstins.find((item) => item.id === params.gstinId);
    if (registration === undefined) return errorResponse(404, "not_found", "No such registration.");
    const parsed = lutBody.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        Object.fromEntries(
          parsed.error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
        ),
      );
    }
    const { valid_from: from, valid_to: to } = parsed.data;
    const arn = parsed.data.arn.toUpperCase();
    if (to < from || financialYear(from) !== financialYear(to)) {
      return errorResponse(
        422,
        "lut_dates",
        "A LUT covers one financial year, 1 April to 31 March.",
      );
    }
    if (mockDb.sellerGstins.some((item) => item.luts.some((lut) => lut.arn === arn))) {
      return errorResponse(409, "lut_duplicate", "That ARN is already recorded.");
    }
    if (registration.luts.some((lut) => overlaps(lut, from, to))) {
      return errorResponse(
        409,
        "lut_overlap",
        "Another LUT of this registration covers some of those dates.",
      );
    }
    issued += 1;
    const lut: LutWire = {
      id: mockUuid(SELLER_GSTIN_SPACE, 500 + issued),
      arn,
      valid_from: from,
      valid_to: to,
      in_use: false,
    };
    registration.luts.push(lut);
    registration.luts.sort((left, right) => right.valid_from.localeCompare(left.valid_from));
    return HttpResponse.json({ data: lut }, { status: 201 });
  }),

  http.delete(buildApiUrl("/seller-gstins/:gstinId/luts/:lutId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return errorResponse(403, "forbidden", "Needs products.edit.");
    const registration = mockDb.sellerGstins.find((item) => item.id === params.gstinId);
    const lut = registration?.luts.find((item) => item.id === params.lutId);
    if (registration === undefined || lut === undefined) {
      return errorResponse(404, "not_found", "No such LUT.");
    }
    if (lut.in_use) {
      return errorResponse(409, "lut_in_use", "A quotation or order carries this LUT.");
    }
    registration.luts = registration.luts.filter((item) => item.id !== lut.id);
    return new HttpResponse(null, { status: 204 });
  }),
];
