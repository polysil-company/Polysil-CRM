import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { isApiError } from "@/lib/api/errors";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockDb, resetMockDb } from "@/mocks/db";

import { checkImport, commitImport, discardImport, uploadImport } from "./imports.api";
import { importRefusal } from "../lib/import-refusals";

let keys = 0;
function key(): string {
  keys += 1;
  return `imports-test-${String(keys)}`;
}

async function refusal(call: Promise<unknown>): Promise<{ status: number; code: string | null }> {
  try {
    await call;
  } catch (error) {
    if (isApiError(error)) return { status: error.status ?? 0, code: error.code ?? null };
    throw error;
  }
  throw new Error("Expected the call to be refused");
}

function csv(name: string, text: string): File {
  return new File([text], name, { type: "text/csv" });
}

function draftList(): string {
  const list = mockDb.priceLists.find((item) => item.status === "draft");
  if (list === undefined) throw new Error("No draft price list");
  return list.id;
}

const RATES = [
  "Item Code,Net Rate",
  "PL-1001,15.20",
  "PL-1002,3.955",
  "PL-9999,120",
  'PL-1003,"4,999"',
].join("\n");

describe("[MSTR-007] Excel import — price list rates", () => {
  beforeEach(() => {
    writeMockRole("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("reads the headers and five sample rows, and suggests a match", async () => {
    const batch = await uploadImport({
      kind: "price_list_items",
      file: csv("rates.csv", RATES),
      targetId: draftList(),
      idempotencyKey: key(),
    });

    expect(batch.headers).toEqual(["Item Code", "Net Rate"]);
    expect(batch.rowCount).toBe(4);
    expect(batch.sample[0]).toEqual(["PL-1001", "15.20"]);
    expect(batch.sheets).toEqual([]);
    expect(batch.suggestedMapping).toEqual({ item_code: 0, rate: 1 });
    expect(batch.fields.find((field) => field.key === "rate")?.required).toBe(true);
  });

  it("checks every row, naming each bad one, and imports the good ones on request", async () => {
    const listId = draftList();
    const batch = await uploadImport({
      kind: "price_list_items",
      file: csv("rates.csv", RATES),
      targetId: listId,
      idempotencyKey: key(),
    });
    const check = await checkImport({
      batchId: batch.id,
      body: { mapping: { item_code: 0, rate: 1 }, options: { mode: "merge" } },
      idempotencyKey: key(),
    });

    expect(check).toMatchObject({ total: 4, ok: 2, errors: 2 });
    expect(check.errorRows).toEqual([
      { row: 3, errors: { rate: "at most two decimals" } },
      { row: 4, errors: { item_code: "no product with item code PL-9999" } },
    ]);
    // As the backend previews it: the product found, its id, and the rate as it will be saved.
    expect(check.preview[0]?.values).toMatchObject({
      product: mockDb.products.find((item) => item.item_code === "PL-1001")?.description,
      rate: "15.20",
    });

    // All or nothing: a bad row refuses the whole import, naming it.
    const refused = await commitImport({
      batchId: batch.id,
      skipInvalid: false,
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(importRefusal(refused).rows).toContainEqual({
      row: 4,
      field: "item_code",
      reason: "no product with item code PL-9999",
    });

    const before = mockDb.priceLists.find((item) => item.id === listId)?.rates.size ?? 0;
    const result = await commitImport({
      batchId: batch.id,
      skipInvalid: true,
      idempotencyKey: key(),
    });
    expect(result).toEqual({ created: 2, skipped: 2 });
    const rates = mockDb.priceLists.find((item) => item.id === listId)?.rates;
    expect(rates?.get(mockDb.products.find((item) => item.item_code === "PL-1001")?.id ?? "")).toBe(
      "15.20",
    );
    // Merge keeps the list's other rates.
    expect(rates?.size ?? 0).toBeGreaterThanOrEqual(before);

    // A committed import is finished.
    expect(
      await refusal(
        checkImport({
          batchId: batch.id,
          body: { mapping: { item_code: 0, rate: 1 } },
          idempotencyKey: key(),
        }),
      ),
    ).toEqual({
      status: 409,
      code: "import_wrong_state",
    });
  });

  it("refuses a mapping it can't check, on the field", async () => {
    const batch = await uploadImport({
      kind: "price_list_items",
      file: csv("rates.csv", RATES),
      targetId: draftList(),
      idempotencyKey: key(),
    });
    const error = await checkImport({
      batchId: batch.id,
      body: { mapping: { item_code: 0 } },
      idempotencyKey: key(),
    }).catch((caught: unknown) => caught);

    expect(importRefusal(error).mapping).toEqual({ rate: "required" });
  });

  it("refuses a file it can't read, one too big, a published list and someone without pricing.edit", async () => {
    const pdf = new File(["%PDF"], "rates.pdf", { type: "application/pdf" });
    const unreadable = await uploadImport({
      kind: "price_list_items",
      file: pdf,
      targetId: draftList(),
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(importRefusal(unreadable).message).toMatch(/Save it as \.xlsx or \.csv/);

    const big = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "big.csv", { type: "text/csv" });
    const tooBig = await uploadImport({
      kind: "price_list_items",
      file: big,
      targetId: draftList(),
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(importRefusal(tooBig).message).toBe("Files up to 10 MB.");

    const published = mockDb.priceLists.find((item) => item.status === "published");
    const onPublished = await uploadImport({
      kind: "price_list_items",
      file: csv("rates.csv", RATES),
      targetId: published?.id,
      idempotencyKey: key(),
    }).catch((error: unknown) => error);
    expect(importRefusal(onPublished)).toMatchObject({
      message: "This list is published. Make a new draft to import into.",
      finished: true,
    });

    writeMockRole("employee");
    expect(
      await refusal(
        uploadImport({
          kind: "price_list_items",
          file: csv("rates.csv", RATES),
          targetId: draftList(),
          idempotencyKey: key(),
        }),
      ),
    ).toEqual({ status: 403, code: "forbidden" });
  });

  it("answers an Excel workbook with its sheets, and reads another sheet on request", async () => {
    const file = new File(["xlsx"], "rates.xlsx");
    const batch = await uploadImport({
      kind: "price_list_items",
      file,
      targetId: draftList(),
      idempotencyKey: key(),
    });
    expect(batch.sheets).toEqual(["Rates", "Notes"]);
    expect(batch.sheet).toBe("Rates");

    const notes = await uploadImport({
      kind: "price_list_items",
      file,
      targetId: draftList(),
      sheet: "Notes",
      idempotencyKey: key(),
    });
    expect(notes.headers).toEqual(["Note"]);
  });

  it("discards an import closed without committing", async () => {
    const batch = await uploadImport({
      kind: "price_list_items",
      file: csv("rates.csv", RATES),
      targetId: draftList(),
      idempotencyKey: key(),
    });
    await discardImport({ batchId: batch.id, idempotencyKey: key() });

    expect(mockDb.imports.get(batch.id)?.status).toBe("discarded");
  });
});

describe("[MSTR-007] Excel import — order and quotation lines", () => {
  beforeEach(() => {
    writeMockRole("employee");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("admin");
  });

  it("returns every good row for the line editor, and has no commit", async () => {
    const batch = await uploadImport({
      kind: "lines",
      file: csv(
        "order.csv",
        [
          "Particulars,Qty,Disc %",
          "INLINE DRIPPER 4 LPH,120,5",
          "NOT A PRODUCT,2,",
          "PL-1001,0,",
        ].join("\n"),
      ),
      idempotencyKey: key(),
    });
    expect(batch.suggestedMapping).toMatchObject({ description: 0, qty: 1, discount_pct: 2 });

    const check = await checkImport({
      batchId: batch.id,
      body: { mapping: batch.suggestedMapping },
      idempotencyKey: key(),
    });
    expect(check).toMatchObject({ total: 3, ok: 1, errors: 2 });
    expect(check.lines).toEqual([
      {
        row: 2,
        productId: mockDb.products.find((item) => item.description === "INLINE DRIPPER 4 LPH")?.id,
        product: "INLINE DRIPPER 4 LPH",
        qty: "120",
        discounts: ["5", "0", "0"],
      },
    ]);

    expect(
      await refusal(commitImport({ batchId: batch.id, skipInvalid: true, idempotencyKey: key() })),
    ).toEqual({ status: 409, code: "import_wrong_state" });
  });
});
