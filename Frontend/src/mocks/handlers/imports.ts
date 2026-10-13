import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  type ImportCheckWire,
  type ImportKind,
  IMPORT_KINDS,
} from "@/features/imports/api/imports.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can, type ModuleCode, type PermissionAction } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import {
  MOCK_IMPORT_FIELDS,
  MOCK_SAMPLE_WORKBOOKS,
  headerKey,
  mappingProblems,
  nameHeaders,
  parseCsv,
  suggestMapping,
  type MockImportBatch,
  type MockSheet,
} from "@/mocks/data/imports";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { withCounts, type MockProductRecord } from "@/mocks/data/products";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse, readMultipart } from "./shared";

/**
 * MSTR-007 · The Excel import (backend `docs/api/imports.md`): upload, check against a mapping,
 * commit, discard. Each kind needs its permission; partner and price imports are staff only.
 * The mock reads a `.csv` itself and answers any `.xlsx` with its kind's sample workbook.
 */

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_ROWS = 5000;
const MAX_ERROR_ROWS = 500;
const PREVIEW_ROWS = 20;
const SAMPLE_ROWS = 5;

const PERMISSIONS: Readonly<
  Record<ImportKind, readonly (readonly [ModuleCode, PermissionAction])[]>
> = {
  partners: [["partners", "create"]],
  price_list_items: [["pricing", "edit"]],
  lines: [
    ["sales_orders", "create"],
    ["quotations", "create"],
  ],
};

const STAFF_ONLY: readonly ImportKind[] = ["partners", "price_list_items"];

function permitted(kind: ImportKind): boolean {
  const role = readMockRole();
  const permissions = mockPermissionsFor(role);
  const held = PERMISSIONS[kind].some(([module, action]) => can(permissions, module, action));
  return held && !(STAFF_ONLY.includes(kind) && isPartnerRole(role));
}

function needsKey(request: Request): Response | null {
  return request.headers.get("idempotency-key") === null
    ? errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.")
    : null;
}

function findBatch(batchId: unknown): MockImportBatch | undefined {
  const batch = mockDb.imports.get(String(batchId));
  return batch === undefined || batch.owner !== readMockRole() ? undefined : batch;
}

function notFound(): Response {
  return errorResponse(404, "not_found", "No such import.");
}

/** The sheet chosen, or the first; and the header row chosen, or the first non-empty one. */
function readSheet(
  sheets: readonly MockSheet[],
  sheetName: string | null,
  headerRow: number | null,
): { sheet: MockSheet | undefined; headerRow: number } {
  const sheet = sheetName === null ? sheets[0] : sheets.find((item) => item.name === sheetName);
  const first = (sheet?.rows.findIndex((row) => row.some((cell) => cell !== "")) ?? 0) + 1;
  return { sheet, headerRow: headerRow ?? first };
}

// ── what each row means, per kind ─────────────────────────────────────────────

interface RowResult {
  readonly values: Record<string, string | null>;
  readonly errors: Record<string, string>;
  readonly line?: NonNullable<ImportCheckWire["lines"]>[number];
}

type Evaluate = (
  rows: MockImportBatch["rows"],
  mapping: Readonly<Record<string, number>>,
) => RowResult[];

function cellOf(
  cells: readonly string[],
  mapping: Readonly<Record<string, number>>,
  key: string,
): string {
  const column = mapping[key];
  return column === undefined ? "" : (cells[column] ?? "").trim();
}

/** The catalogue product a row names, by item code first, then by its exact description. */
function productFor(code: string, description: string): MockProductRecord | undefined {
  if (code !== "") {
    return mockDb.products.find(
      (product) => headerKey(product.item_code ?? "") === headerKey(code),
    );
  }
  return mockDb.products.find(
    (product) => product.description.trim().toLowerCase() === description.trim().toLowerCase(),
  );
}

/** The backend's reasons (`domain/imports/rows.py`), word for word. */
function productProblem(code: string, description: string): Record<string, string> | null {
  if (code === "" && description === "") return { item_code: "required" };
  if (productFor(code, description) === undefined) {
    return code === ""
      ? { description: `no product '${description}'` }
      : { item_code: `no product with item code ${code}` };
  }
  return null;
}

/** What the backend previews for a product: its id and its description, as found. */
function productValues(product: MockProductRecord | undefined): Record<string, string | null> {
  return product === undefined ? {} : { product_id: product.id, product: product.description };
}

function percent(value: string): string | null {
  if (value === "") return "0";
  return /^\d+(\.\d+)?$/.test(value) && Number(value) <= 100 ? String(Number(value)) : null;
}

const EVALUATE: Partial<Record<ImportKind, Evaluate>> = {
  price_list_items: (rows, mapping) =>
    rows.map(({ cells }) => {
      const code = cellOf(cells, mapping, "item_code");
      const description = cellOf(cells, mapping, "description");
      const rate = cellOf(cells, mapping, "rate").replace(/,/g, "");
      const errors: Record<string, string> = { ...productProblem(code, description) };
      if (rate === "") errors.rate = "required";
      else if (!/^\d+(\.\d+)?$/.test(rate)) errors.rate = "not a number";
      else if ((rate.split(".")[1]?.length ?? 0) > 2) errors.rate = "at most two decimals";
      else if (Number(rate) <= 0) errors.rate = "more than 0";
      const product = productFor(code, description);
      return {
        errors,
        values: {
          ...productValues(product),
          rate: errors.rate === undefined ? Number(rate).toFixed(2) : rate,
        },
      };
    }),
  lines: (rows, mapping) =>
    rows.map(({ row, cells }) => {
      const code = cellOf(cells, mapping, "item_code");
      const description = cellOf(cells, mapping, "description");
      const qty = cellOf(cells, mapping, "qty");
      const discounts = (["discount_pct", "discount2_pct", "discount3_pct"] as const).map((key) =>
        percent(cellOf(cells, mapping, key)),
      );
      const errors: Record<string, string> = { ...productProblem(code, description) };
      if (!/^\d+(\.\d+)?$/.test(qty) || Number(qty) <= 0) errors.qty = "more than 0";
      (["discount_pct", "discount2_pct", "discount3_pct"] as const).forEach((key, index) => {
        if (discounts[index] === null) errors[key] = "0 to 100";
      });
      const product = productFor(code, description);
      const values = {
        ...productValues(product),
        qty,
        discount_pct: discounts[0] ?? "",
        discount2_pct: discounts[1] ?? "",
        discount3_pct: discounts[2] ?? "",
      };
      return product === undefined || Object.keys(errors).length > 0
        ? { errors, values }
        : {
            errors,
            values,
            line: {
              row,
              product_id: product.id,
              product: product.description,
              qty,
              discount_pct: discounts[0] ?? "0",
              discount2_pct: discounts[1] ?? "0",
              discount3_pct: discounts[2] ?? "0",
            },
          };
    }),
};

function checkOf(batch: MockImportBatch, results: readonly RowResult[]): ImportCheckWire {
  const mapping = batch.mapping ?? {};
  const bad = results
    .map((result, index) => ({ row: batch.rows[index]?.row ?? 0, errors: result.errors }))
    .filter((result) => Object.keys(result.errors).length > 0);
  const good = results
    .map((result, index) => ({ row: batch.rows[index]?.row ?? 0, result }))
    .filter(({ result }) => Object.keys(result.errors).length === 0);
  const columnWarnings: Record<string, string> = {};
  for (const key of Object.keys(mapping)) {
    if (batch.rows.every(({ cells }) => cellOf(cells, mapping, key) === "")) {
      columnWarnings[key] = "Empty on every row.";
    }
  }
  return {
    total: results.length,
    ok: good.length,
    errors: bad.length,
    error_rows: bad.slice(0, MAX_ERROR_ROWS),
    preview: good.slice(0, PREVIEW_ROWS).map(({ row, result }) => ({ row, values: result.values })),
    column_warnings: columnWarnings,
    lines:
      batch.wire.kind === "lines"
        ? good.flatMap(({ result }) => (result.line === undefined ? [] : [result.line]))
        : null,
  };
}

/** Saves a checked partner or rate import; the good rows only, as the commit asks. */
const COMMIT: Partial<
  Record<ImportKind, (batch: MockImportBatch, good: readonly RowResult[]) => number>
> = {
  price_list_items: (batch, good) => {
    const list = mockDb.priceLists.find((item) => item.id === batch.wire.target_id);
    if (list === undefined) return 0;
    const rates =
      batch.options.mode === "replace" ? new Map<string, string>() : new Map(list.rates);
    for (const { values } of good) {
      const productId = values.product_id;
      const rate = values.rate;
      if (typeof productId === "string" && typeof rate === "string") rates.set(productId, rate);
    }
    list.rates = rates;
    mockDb.priceLists = mockDb.priceLists.map((item) => withCounts(item, mockDb.products));
    return good.length;
  },
};

const checkBodySchema = z.object({
  mapping: z.record(z.string(), z.number().int()),
  options: z.object({ mode: z.enum(["replace", "merge"]).optional() }).optional(),
});

export const importHandlers = [
  http.post(buildApiUrl("/imports"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const form = await readMultipart(request);
    const kind = IMPORT_KINDS.find((value) => value === form.get("kind"));
    const file = form.get("file");
    if (kind === undefined || file === undefined || typeof file === "string") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        ...(kind === undefined ? { kind: "partners, price_list_items or lines" } : {}),
        ...(file === undefined || typeof file === "string" ? { file: "Field required" } : {}),
      });
    }
    if (!permitted(kind)) return errorResponse(403, "forbidden", "No permission for this import.");
    if (file.size > MAX_BYTES) {
      return errorResponse(413, "attachment_too_large", "Files up to 10 MB.");
    }
    const targetValue = form.get("target_id");
    const targetId = typeof targetValue === "string" && targetValue !== "" ? targetValue : null;
    if (kind === "price_list_items") {
      const list = mockDb.priceLists.find((item) => item.id === targetId);
      if (list === undefined) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          target_id: "the draft price list to fill",
        });
      }
      if (list.status === "published") {
        return errorResponse(409, "price_list_published", "That list is published.");
      }
    }
    const name = file.name.toLowerCase();
    let sheets: readonly MockSheet[];
    if (name.endsWith(".csv")) {
      sheets = [{ name: "", rows: parseCsv(new TextDecoder().decode(file.bytes)) }];
    } else if (name.endsWith(".xlsx")) {
      sheets = MOCK_SAMPLE_WORKBOOKS[kind];
    } else {
      return errorResponse(
        422,
        "import_unreadable",
        "That file isn't an Excel workbook or a CSV. Save it as .xlsx or .csv, then upload it again.",
      );
    }
    const sheetValue = form.get("sheet");
    const headerValue = form.get("header_row");
    const { sheet, headerRow } = readSheet(
      sheets,
      typeof sheetValue === "string" && sheetValue !== "" ? sheetValue : null,
      typeof headerValue === "string" && headerValue !== "" ? Number(headerValue) : null,
    );
    if (sheet === undefined || sheet.rows.length < headerRow) {
      return errorResponse(422, "import_unreadable", "That sheet has no rows under its header.");
    }
    const headers = nameHeaders(sheet.rows[headerRow - 1] ?? []);
    const rows = sheet.rows
      .slice(headerRow)
      .map((cells, index) => ({ row: headerRow + index + 1, cells }))
      .filter(({ cells }) => cells.some((cell) => cell.trim() !== ""));
    if (rows.length > MAX_ROWS) {
      return errorResponse(
        422,
        "import_too_many_rows",
        `This sheet has ${String(rows.length)} rows; 5,000 at most. Split it into smaller files.`,
      );
    }
    const id = mockUuid(MOCK_ID_SPACE.importBatch, mockDb.imports.size + 1);
    const isCsv = name.endsWith(".csv");
    const batch: MockImportBatch = {
      wire: {
        id,
        kind,
        status: "uploaded",
        target_id: targetId,
        file_name: file.name,
        sheet: isCsv ? null : sheet.name,
        sheets: isCsv ? [] : sheets.map((item) => item.name),
        header_row: headerRow,
        row_count: rows.length,
        headers,
        sample: rows
          .slice(0, SAMPLE_ROWS)
          .map(({ cells }) => headers.map((_, index) => cells[index] ?? "")),
        fields: MOCK_IMPORT_FIELDS[kind].map(({ aliases: _aliases, ...field }) => field),
        suggested_mapping: suggestMapping(kind, headers),
        mapping: null,
        check: null,
        created_at: new Date().toISOString(),
      },
      rows,
      sheets,
      owner: readMockRole(),
      status: "uploaded",
      mapping: null,
      options: { mode: "replace" },
      check: null,
    };
    mockDb.imports.set(id, batch);
    return HttpResponse.json({ data: batch.wire }, { status: 201 });
  }),

  http.get(buildApiUrl("/imports/:batchId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const batch = findBatch(params.batchId);
    if (batch === undefined) return notFound();
    return HttpResponse.json({
      data: { ...batch.wire, status: batch.status, mapping: batch.mapping, check: batch.check },
    });
  }),

  http.post(buildApiUrl("/imports/:batchId/check"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const batch = findBatch(params.batchId);
    if (batch === undefined) return notFound();
    if (batch.status === "committed" || batch.status === "discarded") {
      return errorResponse(409, "import_wrong_state", "This import is finished.");
    }
    const parsed = checkBodySchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        mapping: "field key to column index",
      });
    }
    const problems = mappingProblems(
      batch.wire.kind,
      parsed.data.mapping,
      batch.wire.headers.length,
    );
    if (Object.keys(problems).length > 0) {
      return errorResponse(422, "validation_error", "The mapping can't be checked.", problems);
    }
    const evaluate = EVALUATE[batch.wire.kind];
    if (evaluate === undefined) return errorResponse(501, "not_implemented", "Not in the mock.");
    batch.mapping = parsed.data.mapping;
    batch.options = { mode: parsed.data.options?.mode ?? "replace" };
    batch.check = checkOf(batch, evaluate(batch.rows, parsed.data.mapping));
    batch.status = "checked";
    return HttpResponse.json({ data: batch.check });
  }),

  http.post(buildApiUrl("/imports/:batchId/commit"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const batch = findBatch(params.batchId);
    if (batch === undefined) return notFound();
    const commit = COMMIT[batch.wire.kind];
    const evaluate = EVALUATE[batch.wire.kind];
    if (
      batch.status !== "checked" ||
      batch.mapping === null ||
      commit === undefined ||
      evaluate === undefined
    ) {
      return errorResponse(409, "import_wrong_state", "This import can't be committed.");
    }
    if (batch.wire.kind === "price_list_items") {
      const list = mockDb.priceLists.find((item) => item.id === batch.wire.target_id);
      if (list?.status === "published") {
        return errorResponse(409, "price_list_published", "That list is published.");
      }
    }
    const body = z.object({ skip_invalid: z.boolean().optional() }).safeParse(await request.json());
    const skipInvalid = body.success && body.data.skip_invalid === true;
    // Every row again: masters may have changed since the check.
    const results = evaluate(batch.rows, batch.mapping);
    const bad = results.flatMap((result, index) =>
      Object.entries(result.errors).map(
        ([field, reason]) =>
          [`rows[${String(batch.rows[index]?.row ?? 0)}].${field}`, reason] as const,
      ),
    );
    if (bad.length > 0 && !skipInvalid) {
      return errorResponse(
        422,
        "import_has_errors",
        "Some rows have errors.",
        Object.fromEntries(bad.slice(0, MAX_ERROR_ROWS)),
      );
    }
    const good = results.filter((result) => Object.keys(result.errors).length === 0);
    const created = commit(batch, good);
    batch.status = "committed";
    return HttpResponse.json({
      data: {
        status: "committed",
        created,
        skipped: results.length - good.length,
        price_list_id: batch.wire.kind === "price_list_items" ? batch.wire.target_id : null,
      },
    });
  }),

  http.delete(buildApiUrl("/imports/:batchId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const batch = findBatch(params.batchId);
    if (batch === undefined) return notFound();
    if (batch.status === "committed") {
      return errorResponse(409, "import_wrong_state", "This import is committed.");
    }
    batch.status = "discarded";
    return new HttpResponse(null, { status: 204 });
  }),
];
