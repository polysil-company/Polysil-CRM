import { z } from "zod";

/**
 * MSTR-004…006 · The product master: the catalogue, each product's tariff heading and each
 * heading's GST slab (dated facts), and the price lists (`backend/docs/api/products.md`,
 * `pricing.md`, handover `products-and-pricing.md`). Money and quantities are decimal strings
 * both ways; nothing here is added up on screen.
 */

const id = z.string().min(1);
const isoDate = z.iso.date();
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

export const QUOTATION_CATEGORIES = ["head", "field", "both"] as const;
export type QuotationCategory = (typeof QUOTATION_CATEGORIES)[number];

/** The figures a product row may still hold as the backend's stand-ins. */
export const PROVISIONAL_FIELDS = ["hsn_code", "gst_slab", "mrp", "pack_multiple"] as const;
export type ProvisionalField = (typeof PROVISIONAL_FIELDS)[number];

/** The slabs the backend accepts; a new one arrives as a migration, never as data entry. */
export const GST_SLABS = ["0", "0.25", "3", "5", "12", "18", "28"] as const;

export const CHANNEL_TIERS = ["distributor", "dealer", "sub_dealer", "farmer"] as const;
export type ChannelTier = (typeof CHANNEL_TIERS)[number];

/**
 * MSTR-008 · The sale types a price list may be for (FS-061). A quotation or order of that type
 * prices from it before any general list; a list with none is general and prices every type.
 */
export const PRICE_LIST_SALES_TYPES = ["commercial", "industrial", "subsidised"] as const;
export type PriceListSalesType = (typeof PRICE_LIST_SALES_TYPES)[number];
/** The list filter: one sale type, or `general` for the lists with none. */
export type PriceListSalesTypeFilter = PriceListSalesType | "general";

const offsetMetaSchema = z.object({
  page: z.number().int().positive(),
  limit: z.number().int().positive(),
  total: z.number().int().nonnegative(),
});

/** One page of an offset-paged list, as screens read it. */
export interface OffsetPage<TItem> {
  readonly items: readonly TItem[];
  readonly page: number;
  readonly limit: number;
  readonly total: number;
}

// ── products ────────────────────────────────────────────────────────────────────

const productWireSchema = z.object({
  id,
  item_code: z.string().nullable(),
  description: z.string(),
  product_category: z.string(),
  quotation_category: z.enum(QUOTATION_CATEGORIES),
  uom: z.string(),
  uom_decimals: z.number().int().nonnegative(),
  hsn_code: z.string().nullable(),
  gst_slab: decimal.nullable(),
  mrp: decimal.nullable(),
  pack_multiple: decimal.nullable(),
  is_subsidy_eligible: z.boolean(),
  is_active: z.boolean(),
  /** Unknown names are dropped rather than failing the row. */
  provisional_fields: z.array(z.string()),
});

export type ProductWire = z.input<typeof productWireSchema>;

/** A catalogue row, as screens read it. */
export interface Product {
  readonly id: string;
  readonly itemCode: string | null;
  readonly description: string;
  readonly category: string;
  readonly quotationCategory: QuotationCategory;
  readonly uom: string;
  readonly uomDecimals: number;
  readonly hsnCode: string | null;
  readonly gstSlab: string | null;
  readonly mrp: string | null;
  readonly packMultiple: string | null;
  readonly subsidyEligible: boolean;
  readonly active: boolean;
  /** Which figures are still stand-ins: show it per field. Empty means all are the client's. */
  readonly provisional: readonly ProvisionalField[];
}

function toProduct(wire: z.output<typeof productWireSchema>): Product {
  return {
    id: wire.id,
    itemCode: wire.item_code,
    description: wire.description,
    category: wire.product_category,
    quotationCategory: wire.quotation_category,
    uom: wire.uom,
    uomDecimals: wire.uom_decimals,
    hsnCode: wire.hsn_code,
    gstSlab: wire.gst_slab,
    mrp: wire.mrp,
    packMultiple: wire.pack_multiple,
    subsidyEligible: wire.is_subsidy_eligible,
    active: wire.is_active,
    provisional: PROVISIONAL_FIELDS.filter((field) => wire.provisional_fields.includes(field)),
  };
}

export const productPageSchema = z
  .object({ data: z.array(productWireSchema), meta: offsetMetaSchema })
  .transform(({ data, meta }): OffsetPage<Product> => ({
    items: data.map(toProduct),
    page: meta.page,
    limit: meta.limit,
    total: meta.total,
  }));

export const productSchema = z
  .object({ data: productWireSchema })
  .transform(({ data }) => toProduct(data));

/** GET /products filters. `active` null lists both. */
export interface ProductListParams {
  readonly q: string;
  readonly category: string | null;
  readonly quotationCategory: QuotationCategory | null;
  readonly active: boolean | null;
}

/** POST /products */
export interface CreateProductRequest {
  readonly description: string;
  readonly product_category: string;
  readonly quotation_category: QuotationCategory;
  readonly uom: string;
  readonly item_code: string | null;
  readonly mrp: string | null;
  readonly pack_multiple: string | null;
  readonly is_subsidy_eligible: boolean;
}

/** PATCH /products/{id}: only what changes. Setting a figure confirms it as the client's. */
export interface PatchProductRequest {
  readonly description?: string;
  readonly product_category?: string;
  readonly quotation_category?: QuotationCategory;
  readonly uom?: string;
  readonly item_code?: string | null;
  readonly mrp?: string | null;
  readonly pack_multiple?: string | null;
  readonly is_subsidy_eligible?: boolean;
  readonly is_active?: boolean;
}

// ── tax classification ─────────────────────────────────────────────────────────

const hsnRowSchema = z.object({
  id,
  hsn_code: z.string(),
  effective_from: isoDate,
  /** Exclusive; null while in force. */
  effective_to: isoDate.nullable(),
});

export type HsnRowWire = z.input<typeof hsnRowSchema>;

export const hsnHistorySchema = z.object({ data: z.array(hsnRowSchema) }).transform(({ data }) =>
  data.map((row) => ({
    id: row.id,
    hsnCode: row.hsn_code,
    from: row.effective_from,
    to: row.effective_to,
  })),
);

export type HsnRow = z.output<typeof hsnHistorySchema>[number];

const taxRateWireSchema = z.object({
  id,
  hsn_code: z.string(),
  rate: decimal,
  effective_from: isoDate,
  effective_to: isoDate.nullable(),
  is_active: z.boolean(),
});

export type TaxRateWire = z.input<typeof taxRateWireSchema>;

export const taxRatePageSchema = z
  .object({ data: z.array(taxRateWireSchema), meta: offsetMetaSchema })
  .transform(({ data, meta }) => ({
    items: data.map((row) => ({
      id: row.id,
      hsnCode: row.hsn_code,
      rate: row.rate,
      from: row.effective_from,
      to: row.effective_to,
    })),
    page: meta.page,
    limit: meta.limit,
    total: meta.total,
  }));

export type TaxRate = z.output<typeof taxRatePageSchema>["items"][number];

// ── price lists ────────────────────────────────────────────────────────────────

const priceListWireSchema = z.object({
  id,
  name: z.string(),
  state_territory: z.object({ id, name: z.string() }).nullable(),
  channel_tier: z.enum(CHANNEL_TIERS).nullable(),
  status: z.enum(["draft", "published"]),
  published_at: z.string().nullable(),
  effective_from: isoDate,
  effective_to: isoDate.nullable(),
  is_active: z.boolean(),
  is_provisional: z.boolean(),
  item_count: z.number().int().nonnegative(),
  unpriced_count: z.number().int().nonnegative(),
  /** MSTR-008 · Null (or absent, before FS-061): a general list. */
  sales_type: z.enum(PRICE_LIST_SALES_TYPES).nullish(),
});

export type PriceListWire = z.input<typeof priceListWireSchema>;

export interface PriceList {
  readonly id: string;
  readonly name: string;
  /** Null: every state. */
  readonly state: { readonly id: string; readonly name: string } | null;
  /** Null: every tier. */
  readonly tier: ChannelTier | null;
  readonly status: "draft" | "published";
  readonly publishedAt: string | null;
  readonly from: string;
  readonly to: string | null;
  readonly provisional: boolean;
  readonly itemCount: number;
  readonly unpricedCount: number;
  /** Null: a general list, for every sale type. Fixed once created. */
  readonly salesType: PriceListSalesType | null;
}

function toPriceList(wire: z.output<typeof priceListWireSchema>): PriceList {
  return {
    id: wire.id,
    name: wire.name,
    state: wire.state_territory,
    tier: wire.channel_tier,
    status: wire.status,
    publishedAt: wire.published_at,
    from: wire.effective_from,
    to: wire.effective_to,
    provisional: wire.is_provisional,
    itemCount: wire.item_count,
    unpricedCount: wire.unpriced_count,
    salesType: wire.sales_type ?? null,
  };
}

export const priceListPageSchema = z
  .object({ data: z.array(priceListWireSchema), meta: offsetMetaSchema })
  .transform(({ data, meta }): OffsetPage<PriceList> => ({
    items: data.map(toPriceList),
    page: meta.page,
    limit: meta.limit,
    total: meta.total,
  }));

export const priceListSchema = z
  .object({ data: priceListWireSchema })
  .transform(({ data }) => toPriceList(data));

const priceListItemWireSchema = z.object({
  product_id: id,
  description: z.string(),
  uom: z.string(),
  rate: decimal.nullable(),
  is_active: z.boolean(),
});

export interface PriceListItem {
  readonly productId: string;
  readonly description: string;
  readonly uom: string;
  /** Null: this list holds no rate for the product. */
  readonly rate: string | null;
  readonly active: boolean;
}

export const priceListItemsPageSchema = z
  .object({
    data: z.array(priceListItemWireSchema),
    meta: offsetMetaSchema,
    /** Active products this list has no rate for. */
    unpriced: z.number().int().nonnegative(),
  })
  .transform(({ data, meta, unpriced }) => ({
    items: data.map((row): PriceListItem => ({
      productId: row.product_id,
      description: row.description,
      uom: row.uom,
      rate: row.rate,
      active: row.is_active,
    })),
    page: meta.page,
    limit: meta.limit,
    total: meta.total,
    unpriced,
  }));

export type PriceListItemsPage = z.output<typeof priceListItemsPageSchema>;

/** POST /price-lists */
export interface CreatePriceListRequest {
  readonly name: string;
  readonly effective_from: string;
  readonly state_territory_id: string | null;
  readonly channel_tier: ChannelTier | null;
  readonly effective_to: string | null;
  readonly source_note: string | null;
  /** MSTR-008 · Null for every sale type. */
  readonly sales_type: PriceListSalesType | null;
}

export const publishResultSchema = z
  .object({
    data: z.object({ closed_predecessor_id: z.string().nullish() }).loose(),
  })
  .transform(({ data }) => ({ closedPredecessorId: data.closed_predecessor_id ?? null }));

// ── lookups the product form offers (BE-024, BE-027) ────────────────────────────

/** GET /lookups/product-categories — every category, switched-off ones too, in sort order. */
export const productCategoriesSchema = z
  .object({
    data: z.array(
      z.object({
        /** What a scheme's `product_category` target takes. */
        id: z.string().min(1),
        /** What `POST /products` takes as `product_category`. */
        code: z.string().min(1),
        name: z.string().min(1),
        sort_order: z.number().int(),
        is_active: z.boolean(),
      }),
    ),
  })
  .transform(({ data }) =>
    data.map((item) => ({ id: item.id, code: item.code, name: item.name, isActive: item.is_active })),
  );

export type ProductCategoriesWire = z.input<typeof productCategoriesSchema>;
export type ProductCategory = z.output<typeof productCategoriesSchema>[number];

/** GET /lookups/uoms — every unit with the decimals a quantity in it takes. */
export const uomsSchema = z
  .object({
    data: z.array(
      z.object({
        id: z.string().min(1),
        /** What `POST /products` takes as `uom`. */
        code: z.string().min(1),
        name: z.string().min(1),
        decimals: z.number().int().min(0).max(3),
        is_active: z.boolean(),
      }),
    ),
  })
  .transform(({ data }) =>
    data.map((item) => ({
      id: item.id,
      code: item.code,
      name: item.name,
      decimals: item.decimals,
      isActive: item.is_active,
    })),
  );

export type UomsWire = z.input<typeof uomsSchema>;
export type Uom = z.output<typeof uomsSchema>[number];
