import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  CHANNEL_TIERS,
  PRICE_LIST_SALES_TYPES,
  GST_SLABS,
  QUOTATION_CATEGORIES,
  type TaxRateWire,
} from "@/features/products/api/products.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { withCounts, type MockPriceList, type MockProductRecord } from "@/mocks/data/products";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { findMockTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * MSTR-003…006 · The catalogue, its tariff headings and slabs, and the price lists, with the
 * backend's rules (`products.md`, `pricing.md`): a unique description, known category and unit
 * codes, dated headings and slabs whose current start date can't be reused, the seven legal
 * slabs, drafts filled then published, published rates never edited, and two decimals on a
 * rate, refused rather than rounded.
 */

const DECIMAL = /^\d+(\.\d+)?$/;

function allowed(module: "products" | "pricing", action: "view" | "edit"): boolean {
  return can(mockPermissionsFor(readMockRole()), module, action);
}

function forbidden(what: string): Response {
  return errorResponse(403, "insufficient_permission", `No ${what}.`);
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function needsKey(request: Request): Response | null {
  return request.headers.get("idempotency-key") === null
    ? errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.")
    : null;
}

function normalized(description: string): string {
  return description
    .replace(/[\s ]+/g, " ")
    .trim()
    .toLowerCase();
}

/** The slab in force for a code on a day, from the Council's rates. */
function slabOn(hsnCode: string | null, on: string): string | null {
  if (hsnCode === null) return null;
  const rate = mockDb.taxRates.find(
    (row) =>
      row.hsn_code === hsnCode &&
      row.effective_from <= on &&
      (row.effective_to === null || row.effective_to > on),
  );
  return rate?.rate ?? null;
}

/** The product as the API returns it on a day: heading and slab as they were then. */
function toWire(product: MockProductRecord, on: string): MockProductRecord {
  const history = mockDb.hsnHistory.get(product.id) ?? [];
  const heading =
    history.find(
      (row) => row.effective_from <= on && (row.effective_to === null || row.effective_to > on),
    )?.hsn_code ?? product.hsn_code;
  const slab = slabOn(heading, on);
  const provisional = product.provisional_fields.filter(
    (field) =>
      !(field === "gst_slab" && slab !== null && !product.provisional_fields.includes("hsn_code")),
  );
  return {
    ...product,
    hsn_code: heading,
    gst_slab: slab ?? product.gst_slab,
    provisional_fields: provisional,
  };
}

function units(): Map<string, number> {
  return new Map(mockDb.products.map((product) => [product.uom, product.uom_decimals] as const));
}

function categories(): Set<string> {
  return new Set(mockDb.products.map((product) => product.product_category));
}

const decimalField = z
  .union([z.string(), z.number()])
  .nullish()
  .transform((value) => (value === null || value === undefined ? null : String(value).trim()));

const productCreateSchema = z.object({
  description: z.string().trim().min(1, "Field required"),
  product_category: z.string().min(1, "Field required"),
  quotation_category: z.enum(QUOTATION_CATEGORIES),
  uom: z.string().min(1, "Field required"),
  item_code: z.string().nullish(),
  mrp: decimalField,
  pack_multiple: decimalField,
  is_subsidy_eligible: z.boolean().default(true),
});

const productPatchSchema = z.object({
  description: z.string().trim().min(1).optional(),
  product_category: z.string().optional(),
  quotation_category: z.enum(QUOTATION_CATEGORIES).optional(),
  uom: z.string().optional(),
  item_code: z.string().nullish(),
  mrp: decimalField.optional(),
  pack_multiple: decimalField.optional(),
  is_subsidy_eligible: z.boolean().optional(),
  is_active: z.boolean().optional(),
});

function figureProblems(body: {
  mrp?: string | null;
  pack_multiple?: string | null;
}): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const field of ["mrp", "pack_multiple"] as const) {
    const value = body[field];
    if (value != null && (!DECIMAL.test(value) || Number(value) <= 0)) {
      fields[field] = "a positive number";
    }
  }
  return fields;
}

function refreshCounts(): void {
  mockDb.priceLists = mockDb.priceLists.map((list) => withCounts(list, mockDb.products));
}

function listWire(list: MockPriceList): Omit<MockPriceList, "rates"> {
  const { rates: _rates, ...wire } = withCounts(list, mockDb.products);
  return wire;
}

function pageOf<T>(
  rows: readonly T[],
  url: URL,
  fallbackLimit: number,
  max: number,
): {
  data: T[];
  meta: { page: number; limit: number; total: number };
} {
  const page = Math.max(1, Number(url.searchParams.get("page") ?? "1") || 1);
  const limit = Math.min(
    max,
    Math.max(1, Number(url.searchParams.get("limit") ?? String(fallbackLimit)) || fallbackLimit),
  );
  return {
    data: rows.slice((page - 1) * limit, page * limit),
    meta: { page, limit, total: rows.length },
  };
}

function itemsPage(list: MockPriceList, url: URL): Record<string, unknown> {
  const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
  const unpricedOnly = url.searchParams.get("unpriced") === "true";
  const rows = mockDb.products
    .filter((product) => (q === "" ? true : product.description.toLowerCase().includes(q)))
    .filter((product) => (unpricedOnly ? product.is_active && !list.rates.has(product.id) : true))
    .map((product) => ({
      product_id: product.id,
      description: product.description,
      uom: product.uom,
      rate: list.rates.get(product.id) ?? null,
      is_active: product.is_active,
    }));
  const unpriced = mockDb.products.filter(
    (product) => product.is_active && !list.rates.has(product.id),
  ).length;
  return { ...pageOf(rows, url, 100, 500), unpriced };
}

function findList(listId: unknown): MockPriceList | undefined {
  return mockDb.priceLists.find((list) => list.id === listId);
}

function overlaps(
  a: { from: string; to: string | null },
  b: { from: string; to: string | null },
): boolean {
  return (b.to === null || a.from < b.to) && (a.to === null || b.from < a.to);
}

export const productHandlers = [
  http.get(buildApiUrl("/products"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("products", "view")) return forbidden("products.view");
    const url = new URL(request.url);
    const q = normalized(url.searchParams.get("q") ?? "");
    const category = url.searchParams.get("category");
    const quotationCategory = url.searchParams.get("quotation_category");
    // The backend lists active products unless asked otherwise.
    const active = url.searchParams.get("active") ?? "true";
    const on = url.searchParams.get("as_of") ?? todayInIndia();
    const rows =
      scenario === "empty"
        ? []
        : mockDb.products
            .filter((product) => (q === "" ? true : normalized(product.description).includes(q)))
            .filter((product) => (category === null ? true : product.product_category === category))
            .filter((product) =>
              quotationCategory === null
                ? true
                : product.quotation_category === quotationCategory ||
                  product.quotation_category === "both",
            )
            .filter((product) => String(product.is_active) === active)
            .map((product) => toWire(product, on));
    return HttpResponse.json(pageOf(rows, url, 50, 200));
  }),

  http.post(buildApiUrl("/products"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("products", "edit")) return forbidden("products.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const parsed = productCreateSchema.safeParse(await request.json());
    if (!parsed.success) {
      return invalid(
        Object.fromEntries(
          parsed.error.issues.map((issue) => [issue.path.join("."), issue.message]),
        ),
      );
    }
    const body = parsed.data;
    const fields = figureProblems(body);
    if (!categories().has(body.product_category)) fields.product_category = "not a category code";
    const unitDecimals = units().get(body.uom);
    if (unitDecimals === undefined) fields.uom = "not a unit code";
    if (Object.keys(fields).length > 0) return invalid(fields);
    if (
      mockDb.products.some(
        (product) => normalized(product.description) === normalized(body.description),
      )
    ) {
      return errorResponse(
        409,
        "duplicate_description",
        "A product with this description exists.",
        {
          description: "already in the catalogue",
        },
      );
    }
    const product: MockProductRecord = {
      id: mockUuid(MOCK_ID_SPACE.quotation, 300 + mockDb.products.length),
      item_code: body.item_code?.trim() || null,
      description: body.description.replace(/[\s ]+/g, " ").trim(),
      product_category: body.product_category,
      quotation_category: body.quotation_category,
      uom: body.uom,
      uom_decimals: unitDecimals ?? 0,
      hsn_code: null,
      gst_slab: null,
      mrp: body.mrp,
      pack_multiple: body.pack_multiple,
      is_subsidy_eligible: body.is_subsidy_eligible,
      is_active: true,
      provisional_fields: [],
    };
    mockDb.products.push(product);
    mockDb.hsnHistory.set(product.id, []);
    refreshCounts();
    return HttpResponse.json({ data: toWire(product, todayInIndia()) }, { status: 201 });
  }),

  http.get(buildApiUrl("/products/:productId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const product = mockDb.products.find((item) => item.id === params.productId);
    if (product === undefined) return errorResponse(404, "not_found", "No such product.");
    const on = new URL(request.url).searchParams.get("as_of") ?? todayInIndia();
    return HttpResponse.json({ data: toWire(product, on) });
  }),

  http.patch(buildApiUrl("/products/:productId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("products", "edit")) return forbidden("products.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const product = mockDb.products.find((item) => item.id === params.productId);
    if (product === undefined) return errorResponse(404, "not_found", "No such product.");
    const parsed = productPatchSchema.safeParse(await request.json());
    if (!parsed.success) {
      return invalid(
        Object.fromEntries(
          parsed.error.issues.map((issue) => [issue.path.join("."), issue.message]),
        ),
      );
    }
    const body = parsed.data;
    const fields = figureProblems({
      mrp: body.mrp ?? null,
      pack_multiple: body.pack_multiple ?? null,
    });
    if (body.product_category !== undefined && !categories().has(body.product_category)) {
      fields.product_category = "not a category code";
    }
    const unitDecimals = body.uom === undefined ? undefined : units().get(body.uom);
    if (body.uom !== undefined && unitDecimals === undefined) fields.uom = "not a unit code";
    if (Object.keys(fields).length > 0) return invalid(fields);
    if (
      body.description !== undefined &&
      mockDb.products.some(
        (item) =>
          item.id !== product.id &&
          normalized(item.description) === normalized(body.description ?? ""),
      )
    ) {
      return errorResponse(
        409,
        "duplicate_description",
        "A product with this description exists.",
        {
          description: "already in the catalogue",
        },
      );
    }
    if (body.description !== undefined)
      product.description = body.description.replace(/[\s ]+/g, " ").trim();
    if (body.product_category !== undefined) product.product_category = body.product_category;
    if (body.quotation_category !== undefined) product.quotation_category = body.quotation_category;
    if (body.uom !== undefined && unitDecimals !== undefined) {
      product.uom = body.uom;
      product.uom_decimals = unitDecimals;
    }
    if (body.item_code !== undefined) product.item_code = body.item_code?.trim() || null;
    // Setting a figure confirms it as the client's own, and nothing else.
    if (body.mrp !== undefined) {
      product.mrp = body.mrp;
      product.provisional_fields = product.provisional_fields.filter((field) => field !== "mrp");
    }
    if (body.pack_multiple !== undefined) {
      product.pack_multiple = body.pack_multiple;
      product.provisional_fields = product.provisional_fields.filter(
        (field) => field !== "pack_multiple",
      );
    }
    if (body.is_subsidy_eligible !== undefined)
      product.is_subsidy_eligible = body.is_subsidy_eligible;
    if (body.is_active !== undefined) product.is_active = body.is_active;
    refreshCounts();
    return HttpResponse.json({ data: toWire(product, todayInIndia()) });
  }),

  http.get(buildApiUrl("/products/:productId/hsn"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const history = mockDb.hsnHistory.get(String(params.productId));
    if (history === undefined) return errorResponse(404, "not_found", "No such product.");
    return HttpResponse.json({ data: history });
  }),

  http.put(buildApiUrl("/products/:productId/hsn"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("products", "edit")) return forbidden("products.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const product = mockDb.products.find((item) => item.id === params.productId);
    const history = mockDb.hsnHistory.get(String(params.productId));
    if (product === undefined || history === undefined) {
      return errorResponse(404, "not_found", "No such product.");
    }
    const parsed = z
      .object({ hsn_code: z.string(), effective_from: z.iso.date() })
      .safeParse(await request.json());
    if (!parsed.success) return invalid({ effective_from: "a date" });
    const { hsn_code: code, effective_from: from } = parsed.data;
    if (!/^\d{4,8}$/.test(code)) return invalid({ hsn_code: "four to eight digits" });
    const current = history.find((row) => row.effective_to === null);
    if (current !== undefined && current.effective_from === from) {
      return errorResponse(409, "hsn_same_start_date", "The heading in force starts that day.");
    }
    if (current !== undefined && from < current.effective_from) {
      return invalid({ effective_from: "after the heading in force starts" });
    }
    if (current !== undefined) current.effective_to = from;
    history.unshift({
      id: mockUuid(MOCK_ID_SPACE.lookup, 0x700 + history.length + mockDb.products.length * 10),
      hsn_code: code,
      effective_from: from,
      effective_to: null,
    });
    if (from <= todayInIndia()) product.hsn_code = code;
    product.provisional_fields = product.provisional_fields.filter(
      (field) => field !== "hsn_code" && !(field === "gst_slab" && slabOn(code, from) !== null),
    );
    return HttpResponse.json({ data: history });
  }),

  http.get(buildApiUrl("/tax-rates"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const url = new URL(request.url);
    const code = url.searchParams.get("hsn_code");
    const inForce = url.searchParams.get("in_force") === "true";
    const today = todayInIndia();
    const rows = mockDb.taxRates
      .filter((row) => (code === null || code === "" ? true : row.hsn_code === code))
      .filter((row) =>
        inForce
          ? row.effective_from <= today && (row.effective_to === null || row.effective_to > today)
          : true,
      )
      .sort(
        (a, b) =>
          a.hsn_code.localeCompare(b.hsn_code) || b.effective_from.localeCompare(a.effective_from),
      );
    return HttpResponse.json(pageOf(rows, url, 50, 200));
  }),

  http.put(buildApiUrl("/tax-rates/:hsnCode"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("products", "edit")) return forbidden("products.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const code = String(params.hsnCode);
    if (!/^\d{4,8}$/.test(code)) return invalid({ hsn_code: "four to eight digits" });
    const parsed = z
      .object({ rate: z.union([z.string(), z.number()]), effective_from: z.iso.date() })
      .safeParse(await request.json());
    if (!parsed.success) return invalid({ effective_from: "a date" });
    const rate = String(parsed.data.rate);
    if (!GST_SLABS.some((slab) => Number(slab) === Number(rate))) {
      return invalid({ rate: "one of 0, 0.25, 3, 5, 12, 18, 28" });
    }
    const from = parsed.data.effective_from;
    const current = mockDb.taxRates.find(
      (row) => row.hsn_code === code && row.effective_to === null,
    );
    if (current !== undefined && current.effective_from === from) {
      return errorResponse(409, "tax_rate_same_start_date", "The rate in force starts that day.");
    }
    if (current !== undefined && from < current.effective_from) {
      return invalid({ effective_from: "after the rate in force starts" });
    }
    if (current !== undefined) current.effective_to = from;
    const row: TaxRateWire = {
      id: mockUuid(MOCK_ID_SPACE.lookup, 0x800 + mockDb.taxRates.length),
      hsn_code: code,
      rate: Number(rate).toFixed(3),
      effective_from: from,
      effective_to: null,
      is_active: true,
    };
    mockDb.taxRates.push(row);
    // Every product under the code stops marking its slab a guess.
    for (const product of mockDb.products) {
      if (product.hsn_code === code) {
        product.provisional_fields = product.provisional_fields.filter(
          (field) => field !== "gst_slab",
        );
      }
    }
    const rows = mockDb.taxRates.filter((item) => item.hsn_code === code);
    return HttpResponse.json({ data: rows, meta: { page: 1, limit: 50, total: rows.length } });
  }),

  http.get(buildApiUrl("/price-lists"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("pricing", "view")) return forbidden("pricing.view");
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    // MSTR-008 · One sale type, or `general` for the lists with none.
    const salesType = url.searchParams.get("sales_type");
    const rows =
      scenario === "empty"
        ? []
        : mockDb.priceLists
            .filter((list) => (status === null ? true : list.status === status))
            .filter((list) =>
              salesType === null
                ? true
                : salesType === "general"
                  ? (list.sales_type ?? null) === null
                  : list.sales_type === salesType,
            )
            .sort((a, b) => b.effective_from.localeCompare(a.effective_from))
            .map(listWire);
    return HttpResponse.json(pageOf(rows, url, 50, 100));
  }),

  http.post(buildApiUrl("/price-lists"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("pricing", "edit")) return forbidden("pricing.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const parsed = z
      .object({
        name: z.string().trim().min(1, "Field required"),
        effective_from: z.iso.date(),
        state_territory_id: z.string().nullish(),
        channel_tier: z.enum(CHANNEL_TIERS).nullish(),
        effective_to: z.iso.date().nullish(),
        source_note: z.string().nullish(),
        sales_type: z.enum(PRICE_LIST_SALES_TYPES).nullish(),
      })
      .safeParse(await request.json());
    if (!parsed.success) {
      return invalid(
        Object.fromEntries(
          parsed.error.issues.map((issue) => [issue.path.join("."), issue.message]),
        ),
      );
    }
    const body = parsed.data;
    let state: { id: string; name: string } | null = null;
    if (body.state_territory_id != null) {
      const territory = findMockTerritory(body.state_territory_id);
      if (territory?.level !== "state") return invalid({ state_territory_id: "a state" });
      state = { id: territory.id, name: territory.name };
    }
    if (body.effective_to != null && body.effective_to <= body.effective_from) {
      return invalid({ effective_to: "after the list starts" });
    }
    const list: MockPriceList = {
      id: mockUuid(MOCK_ID_SPACE.quotation, 400 + mockDb.priceLists.length),
      name: body.name,
      state_territory: state,
      channel_tier: body.channel_tier ?? null,
      sales_type: body.sales_type ?? null,
      status: "draft",
      published_at: null,
      effective_from: body.effective_from,
      effective_to: body.effective_to ?? null,
      is_active: true,
      is_provisional: false,
      item_count: 0,
      unpriced_count: 0,
      rates: new Map(),
    };
    mockDb.priceLists.push(list);
    return HttpResponse.json({ data: listWire(list) }, { status: 201 });
  }),

  http.get(buildApiUrl("/price-lists/:listId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const list = findList(params.listId);
    if (list === undefined) return errorResponse(404, "not_found", "No such price list.");
    return HttpResponse.json({ data: listWire(list) });
  }),

  http.patch(buildApiUrl("/price-lists/:listId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("pricing", "edit")) return forbidden("pricing.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const list = findList(params.listId);
    if (list === undefined) return errorResponse(404, "not_found", "No such price list.");
    const parsed = z.object({ effective_to: z.iso.date() }).safeParse(await request.json());
    if (!parsed.success) return invalid({ effective_to: "a date" });
    const to = parsed.data.effective_to;
    if (to <= list.effective_from) return invalid({ effective_to: "later than the list's start" });
    if (to < todayInIndia()) return invalid({ effective_to: "not before today" });
    if (list.effective_to !== null && to > list.effective_to) {
      return invalid({ effective_to: "forward only: not later than it already ends" });
    }
    list.effective_to = to;
    return HttpResponse.json({ data: listWire(list) });
  }),

  http.get(buildApiUrl("/price-lists/:listId/items"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const list = findList(params.listId);
    if (list === undefined) return errorResponse(404, "not_found", "No such price list.");
    return HttpResponse.json(itemsPage(list, new URL(request.url)));
  }),

  http.put(buildApiUrl("/price-lists/:listId/items"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("pricing", "edit")) return forbidden("pricing.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const list = findList(params.listId);
    if (list === undefined) return errorResponse(404, "not_found", "No such price list.");
    if (list.status === "published") {
      return errorResponse(409, "price_list_published", "A published list's rates never change.");
    }
    const parsed = z
      .object({
        items: z
          .array(z.object({ product_id: z.string(), rate: z.union([z.string(), z.number()]) }))
          .max(2000),
      })
      .safeParse(await request.json());
    if (!parsed.success) return invalid({ items: "at most 2,000 items" });
    const fields: Record<string, string> = {};
    const rates = new Map<string, string>();
    for (const [index, item] of parsed.data.items.entries()) {
      const rate = String(item.rate).trim();
      if (!mockDb.products.some((product) => product.id === item.product_id)) {
        fields[`items[${String(index)}].product_id`] = "no such product";
      } else if (!/^\d+(\.\d{1,2})?$/.test(rate)) {
        fields[`items[${String(index)}].rate`] = "at most two decimals";
      } else if (Number(rate) <= 0) {
        fields[`items[${String(index)}].rate`] = "greater than 0";
      } else {
        rates.set(item.product_id, Number(rate).toFixed(2));
      }
    }
    if (Object.keys(fields).length > 0) return invalid(fields);
    list.rates = rates;
    refreshCounts();
    return HttpResponse.json(itemsPage(list, new URL(request.url)));
  }),

  http.post(buildApiUrl("/price-lists/:listId/publish"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("pricing", "edit")) return forbidden("pricing.edit");
    const missingKey = needsKey(request);
    if (missingKey !== null) return missingKey;
    const list = findList(params.listId);
    if (list === undefined) return errorResponse(404, "not_found", "No such price list.");
    if (list.status === "published") {
      return errorResponse(409, "price_list_published", "The list is already published.");
    }
    const parsed = z
      .object({ allow_unpriced: z.boolean().default(false) })
      .safeParse(await request.json().catch(() => ({})));
    const allowUnpriced = parsed.success && parsed.data.allow_unpriced;
    const counted = withCounts(list, mockDb.products);
    if (counted.unpriced_count > 0 && !allowUnpriced) {
      return errorResponse(
        409,
        "price_list_unpriced",
        `${String(counted.unpriced_count)} active products have no rate in this list.`,
      );
    }
    // The published list of the same scope in force on the new start closes first.
    const predecessor = mockDb.priceLists.find(
      (other) =>
        other.id !== list.id &&
        other.status === "published" &&
        (other.state_territory?.id ?? null) === (list.state_territory?.id ?? null) &&
        other.channel_tier === list.channel_tier &&
        (other.sales_type ?? null) === (list.sales_type ?? null) &&
        overlaps(
          { from: other.effective_from, to: other.effective_to },
          { from: list.effective_from, to: list.effective_to },
        ),
    );
    if (predecessor !== undefined) {
      if (predecessor.effective_from >= list.effective_from) {
        return errorResponse(
          409,
          "price_list_overlap",
          "A list of the same scope starts on or after this one.",
        );
      }
      predecessor.effective_to = list.effective_from;
    }
    list.status = "published";
    list.published_at = new Date().toISOString();
    return HttpResponse.json({
      data: { id: list.id, closed_predecessor_id: predecessor?.id ?? null },
    });
  }),
];
