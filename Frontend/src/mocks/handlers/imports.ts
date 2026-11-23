import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  type ImportCheckWire,
  type ImportKind,
  IMPORT_KINDS,
} from "@/features/imports/api/imports.schemas";
import { PARTNER_TYPES, type PartnerType } from "@/features/partners/api/partners.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can, type ModuleCode, type PermissionAction } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { normalizeIndianMobile } from "@/lib/format";
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
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { addMockPartner } from "./partners";
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
  readonly values: Record<string, string | boolean | null>;
  readonly errors: Record<string, string>;
  readonly line?: NonNullable<ImportCheckWire["lines"]>[number];
  /** A partner row's place, kept for the commit and never previewed (CHNL-005). */
  readonly partner?: PartnerPlace;
}

interface PartnerPlace {
  readonly row: number;
  readonly type: PartnerType;
  /** Null while the row's state or district has an error. */
  readonly territoryId: string | null;
  /** An existing partner the row goes under. */
  parentId: string | null;
  /** A row of this file the row goes under. */
  parentRow: number | null;
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

// ── partners (CHNL-005), as backend `domain/imports/rows.py` parse_partners and finish_partners

const PARTNER_TYPE_WORDS: Readonly<Record<string, PartnerType>> = {
  distributor: "distributor",
  dist: "distributor",
  d: "distributor",
  dealer: "dealer",
  subdealer: "sub_dealer",
  sd: "sub_dealer",
  sub: "sub_dealer",
  retailer: "sub_dealer",
};

const GSTIN_PATTERN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const PAN_PATTERN = /^[A-Z]{5}[0-9]{4}[A-Z]$/;

function wrongType(type: PartnerType): string {
  return type === "distributor"
    ? "a distributor has no parent"
    : "wrong type for this parent: the order is distributor > dealer > sub-dealer";
}

function yesNo(text: string): boolean | null {
  const word = headerKey(text);
  if (["yes", "y", "true", "1"].includes(word)) return true;
  if (["no", "n", "false", "0"].includes(word)) return false;
  return null;
}

function evaluatePartners(
  rows: MockImportBatch["rows"],
  mapping: Readonly<Record<string, number>>,
): RowResult[] {
  const states = MOCK_TERRITORIES.filter((territory) => territory.level === "state");
  const results = rows.map(({ row, cells }): RowResult => {
    const get = (key: string): string => cellOf(cells, mapping, key);
    const errors: Record<string, string> = {};
    const rawType = get("partner_type");
    const type = PARTNER_TYPE_WORDS[headerKey(rawType)] ?? null;
    if (rawType === "") errors.partner_type = "required";
    else if (type === null) {
      errors.partner_type = `'${rawType}' is not distributor, dealer or sub-dealer`;
    }
    const code = get("code");
    if (code === "") errors.code = "required";
    const name = get("name");
    if (name === "") errors.name = "required";
    const stateText = get("state");
    const state = states.find(
      (item) =>
        headerKey(item.name) === headerKey(stateText) ||
        headerKey(item.code ?? "") === headerKey(stateText),
    );
    if (stateText === "") errors.state = "required";
    else if (state === undefined) errors.state = `no state '${stateText}'`;
    const districtText = get("district");
    const district =
      districtText === "" || state === undefined
        ? undefined
        : MOCK_TERRITORIES.find(
            (item) =>
              item.level === "district" &&
              item.parent?.id === state.id &&
              headerKey(item.name) === headerKey(districtText),
          );
    if (districtText !== "" && state !== undefined && district === undefined) {
      errors.district = `no district '${districtText}' in ${state.name}`;
    }
    const mobileText = get("mobile");
    const mobile = mobileText === "" ? null : (normalizeIndianMobile(mobileText)?.slice(1) ?? null);
    if (mobileText !== "" && mobile === null) errors.mobile = "not an Indian mobile number";
    const email = get("email").toLowerCase();
    if (email !== "" && !z.email().safeParse(email).success) errors.email = "not an email";
    const gstin = get("gstin").toUpperCase().replace(/ /g, "");
    if (gstin !== "" && !GSTIN_PATTERN.test(gstin)) errors.gstin = "not a GSTIN";
    const pan = get("pan").toUpperCase().replace(/ /g, "");
    if (pan !== "" && !PAN_PATTERN.test(pan)) errors.pan = "not a PAN";
    const registeredText = get("is_gst_registered");
    const registered = registeredText === "" ? gstin !== "" : yesNo(registeredText);
    if (registered === null) errors.is_gst_registered = "yes or no";
    else if (registered && gstin === "") errors.gstin = "required when GST registered";
    const credit = get("credit_limit").replace(/,/g, "");
    if (credit !== "" && !/^\d+(\.\d{1,2})?$/.test(credit)) {
      errors.credit_limit = "at most two decimals, 0 or more";
    }
    const terms = get("payment_terms_days");
    if (terms !== "" && (!/^\d+$/.test(terms) || Number(terms) > 365)) {
      errors.payment_terms_days = "a whole number from 0 to 365";
    }
    const place = district ?? state;
    const territory =
      district !== undefined && state !== undefined
        ? `${district.name}, ${state.name}`
        : (state?.name ?? null);
    const values: Record<string, string | boolean | null> = {
      partner_type: type,
      code,
      name,
      territory,
      parent_code: get("parent_code") === "" ? null : get("parent_code"),
      contact_name: get("contact_name") === "" ? null : get("contact_name"),
      address: get("address") === "" ? null : get("address"),
      mobile,
      email: email === "" ? null : email,
      gstin: gstin === "" ? null : gstin,
      pan: pan === "" ? null : pan,
      is_gst_registered: registered ?? false,
      credit_limit:
        credit === "" || errors.credit_limit !== undefined ? null : Number(credit).toFixed(2),
      payment_terms_days: terms === "" ? null : terms,
    };
    return {
      errors,
      values,
      ...(type === null
        ? {}
        : {
            partner: {
              row,
              type,
              territoryId: place?.id ?? null,
              parentId: null,
              parentRow: null,
            },
          }),
    };
  });

  // A code repeated in the file is wrong on every row that has it: which one was meant?
  const byCode = new Map<string, number[]>();
  rows.forEach(({ row }, index) => {
    const code = String(results[index]?.values.code ?? "").toLowerCase();
    if (code !== "") byCode.set(code, [...(byCode.get(code) ?? []), row]);
  });
  rows.forEach(({ row }, index) => {
    const result = results[index];
    const code = String(result?.values.code ?? "").toLowerCase();
    const same = byCode.get(code) ?? [];
    const other = same.find((item) => item !== row);
    if (result !== undefined && other !== undefined)
      result.errors.code ??= `also on row ${String(other)}`;
  });

  // A code in use is an error, never an update of that partner (GAP-471).
  for (const result of results) {
    const code = String(result.values.code ?? "");
    if (
      code !== "" &&
      mockDb.partners.some((partner) => partner.code.toLowerCase() === code.toLowerCase())
    ) {
      result.errors.code ??= `${code} is already in use`;
    }
  }

  // Parents, settled in type order so a dealer under a distributor with errors has one too.
  const inFile = new Map<string, RowResult>();
  for (const result of results) {
    const code = String(result.values.code ?? "").toLowerCase();
    if (code !== "" && !inFile.has(code)) inFile.set(code, result);
  }
  const rank = (result: RowResult): number =>
    result.partner === undefined
      ? PARTNER_TYPES.length
      : PARTNER_TYPES.indexOf(result.partner.type);
  for (const result of [...results].sort((a, b) => rank(a) - rank(b))) {
    const parentCode = String(result.values.parent_code ?? "");
    const place = result.partner;
    if (parentCode === "" || place === undefined) continue;
    const expected = PARTNER_TYPES[PARTNER_TYPES.indexOf(place.type) - 1];
    const found = inFile.get(parentCode.toLowerCase());
    if (found === result) {
      result.errors.parent_code ??= "a partner cannot be its own parent";
    } else if (found !== undefined) {
      const above = found.partner;
      if (above === undefined || above.type !== expected) {
        result.errors.parent_code ??= wrongType(place.type);
      } else if (Object.keys(found.errors).length > 0) {
        result.errors.parent_code ??= `the parent on row ${String(above.row)} has errors`;
      } else place.parentRow = above.row;
    } else {
      const known = mockDb.partners.find(
        (partner) => partner.code.toLowerCase() === parentCode.toLowerCase(),
      );
      if (known === undefined) result.errors.parent_code ??= `no partner with code ${parentCode}`;
      else if (known.partner_type !== expected) result.errors.parent_code ??= wrongType(place.type);
      else place.parentId = known.id;
    }
  }
  return results;
}

/** Adds the good partner rows, parents first, under the partners or rows they name. */
function commitPartners(good: readonly RowResult[]): number {
  const made = new Map<number, string>();
  const ordered = [...good].sort(
    (a, b) =>
      PARTNER_TYPES.indexOf(a.partner?.type ?? "sub_dealer") -
      PARTNER_TYPES.indexOf(b.partner?.type ?? "sub_dealer"),
  );
  let created = 0;
  for (const { values, partner: place } of ordered) {
    if (place === undefined) continue;
    const parentId =
      place.parentId ?? (place.parentRow === null ? null : (made.get(place.parentRow) ?? null));
    const parent =
      parentId === null ? undefined : mockDb.partners.find((item) => item.id === parentId);
    const territory = MOCK_TERRITORIES.find((item) => item.id === place.territoryId);
    // A good row always has its place; the check names the field otherwise.
    const text = (key: string): string | null => {
      const value = values[key];
      return typeof value === "string" ? value : null;
    };
    const id = addMockPartner({
      code: text("code") ?? "",
      name: text("name") ?? "",
      partner_type: place.type,
      price_tier: place.type,
      parent_id: parent?.id ?? null,
      parent:
        parent === undefined
          ? null
          : { id: parent.id, name: parent.name, partner_type: parent.partner_type },
      territory:
        territory === undefined
          ? null
          : { id: territory.id, name: territory.name, level: territory.level },
      contact_name: text("contact_name"),
      mobile: text("mobile"),
      email: text("email"),
      address: text("address"),
      gstin: text("gstin"),
      pan: text("pan"),
      is_gst_registered: values.is_gst_registered === true,
      credit_limit: text("credit_limit"),
      payment_terms_days:
        text("payment_terms_days") === null ? null : Number(text("payment_terms_days")),
      is_active: true,
    });
    made.set(place.row, id);
    created += 1;
  }
  return created;
}

const EVALUATE: Partial<Record<ImportKind, Evaluate>> = {
  partners: evaluatePartners,
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
  partners: (_batch, good) => commitPartners(good),
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
    // MSTR-013 · the backend names the field it refuses the upload on.
    if (sheet === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        sheet: "No sheet of that name in this workbook.",
      });
    }
    if (sheet.rows.length < headerRow) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        header_row: `This sheet has ${String(sheet.rows.length)} rows; choose one of them.`,
      });
    }
    const after = sheet.rows
      .slice(headerRow)
      .filter((row) => row.some((cell) => cell.trim() !== ""));
    if (after.length === 0) {
      return errorResponse(
        422,
        "import_unreadable",
        "That sheet has no rows under its column names. Fill in the template, then upload it.",
        {
          file: "That sheet has no rows under its column names. Fill in the template, then upload it.",
        },
      );
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

  // MSTR-013 · a blank template for this kind of import: the same permission as the upload.
  http.get(buildApiUrl("/imports/template"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const kind = IMPORT_KINDS.find(
      (value) => value === new URL(request.url).searchParams.get("kind"),
    );
    if (kind === undefined) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        kind: "partners, price_list_items or lines",
      });
    }
    if (!permitted(kind)) return errorResponse(403, "forbidden", "No permission for this import.");
    // Not a real workbook: the mock only needs a file to save.
    const columns = MOCK_IMPORT_FIELDS[kind].map((field) => field.label).join(",");
    return new HttpResponse(`${columns}\n`, {
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
    });
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
