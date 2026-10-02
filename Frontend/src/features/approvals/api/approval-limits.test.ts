import { http, HttpResponse } from "msw";
import { describe, afterEach, expect, it } from "vitest";

import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import { getApprovalThresholds, putApprovalThreshold } from "./approvals.api";
import type { ThresholdPutRequest } from "./approvals.schemas";

let keys = 0;
function put(body: ThresholdPutRequest): ReturnType<typeof putApprovalThreshold> {
  keys += 1;
  return putApprovalThreshold({ body, idempotencyKey: `limits-test-${String(keys)}` });
}

async function refusal(call: Promise<unknown>): Promise<{ status: number; code: string | null }> {
  try {
    await call;
  } catch (error) {
    if (isApiError(error)) {
      return { status: error.status ?? 0, code: error.code ?? null };
    }
    throw error;
  }
  throw new Error("Expected the call to be refused");
}

describe("[APPR-002] approval limits", () => {
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
  });

  it("reads a complaint's refund limits, in rupees on the order's managers", async () => {
    const rows = await getApprovalThresholds();

    expect(rows.filter((row) => row.docType === "complaint")).toEqual([
      expect.objectContaining({ role: "district_manager", maxAmount: "25000.00", unit: "inr" }),
      expect.objectContaining({ role: "state_manager", maxAmount: "100000.00" }),
      expect.objectContaining({ role: "regional_manager", maxAmount: null }),
    ]);
  });

  it("leaves out limits for a document it doesn't know, instead of failing the page", async () => {
    const row = (docType: string): Record<string, unknown> => ({
      doc_type: docType,
      role: "district_manager",
      territory: null,
      max_amount: "100.00",
      unit: "inr",
    });
    server.use(
      http.get(buildApiUrl("/approvals/thresholds"), () =>
        HttpResponse.json({ data: [row("sales_order"), row("complaint"), row("warranty_claim")] }),
      ),
    );

    const rows = await getApprovalThresholds();

    expect(rows.map((item) => item.docType)).toEqual(["sales_order", "complaint"]);
  });

  it("changes a refund limit", async () => {
    writeMockRole("admin");

    const rows = await put({
      doc_type: "complaint",
      role: "district_manager",
      territory_id: null,
      max_amount: "30000.00",
    });

    expect(
      rows.find((item) => item.docType === "complaint" && item.role === "district_manager"),
    ).toMatchObject({ maxAmount: "30000.00", unit: "inr" });
  });

  it("reads every limit: orders in rupees, discounts in percent", async () => {
    const rows = await getApprovalThresholds();
    expect(rows.filter((row) => row.docType === "sales_order" && row.territory === null)).toEqual([
      expect.objectContaining({ role: "district_manager", maxAmount: "100000.00", unit: "inr" }),
      expect.objectContaining({ role: "state_manager", maxAmount: "500000.00" }),
      expect.objectContaining({ role: "regional_manager", maxAmount: null }),
    ]);
    expect(rows.find((row) => row.role === "field_officer")).toMatchObject({
      maxAmount: "5.00",
      unit: "pct",
    });
  });

  it("lets an administrator change a limit, keeping the levels in order", async () => {
    writeMockRole("admin");
    const rows = await put({
      doc_type: "sales_order",
      role: "state_manager",
      territory_id: null,
      max_amount: "400000.00",
    });
    expect(
      rows.find(
        (row) =>
          row.role === "state_manager" && row.docType === "sales_order" && row.territory === null,
      )?.maxAmount,
    ).toBe("400000.00");

    await expect(
      refusal(
        put({
          doc_type: "sales_order",
          role: "state_manager",
          territory_id: null,
          max_amount: "90000.00",
        }),
      ),
    ).resolves.toEqual({ status: 422, code: "thresholds_not_increasing" });
    await expect(
      refusal(
        put({
          doc_type: "quotation",
          role: "district_manager",
          territory_id: null,
          max_amount: null,
        }),
      ),
    ).resolves.toEqual({ status: 422, code: "validation_error" });
    await expect(
      refusal(
        put({ doc_type: "quotation", role: "admin_sales", territory_id: null, max_amount: "150" }),
      ),
    ).resolves.toEqual({ status: 422, code: "validation_error" });
  });

  it("is refused to anyone who may not edit masters", async () => {
    await expect(
      refusal(
        put({
          doc_type: "sales_order",
          role: "district_manager",
          territory_id: null,
          max_amount: "90000.00",
        }),
      ),
    ).resolves.toEqual({ status: 403, code: "forbidden" });
  });
});
