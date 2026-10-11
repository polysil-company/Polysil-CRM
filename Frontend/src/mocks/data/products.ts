import type {
  HsnRowWire,
  PriceListWire,
  ProductWire,
  QuotationCategory,
  TaxRateWire,
} from "@/features/products/api/products.schemas";

import { MOCK_PRODUCTS } from "./quotations";
import { MOCK_ID_SPACE, mockUuid } from "./reference";
import { MOCK_TERRITORIES } from "./territories";

/**
 * MSTR-004…006 · The mock's product master. The six products the quotation mock prices (same
 * ids, same names) come first, then a few more to show the states the catalogue screen has: a
 * product with no tariff heading yet, one whose figures are still stand-ins, one switched off.
 * The quotation mock prices only its own six; a product added here lists but doesn't price.
 */

/** A catalogue row as the mock keeps it, with its own classification history. */
export interface MockProductRecord extends ProductWire {
  provisional_fields: string[];
}

export interface MockPriceList extends PriceListWire {
  /** product id → rate, rupees with two decimals. */
  rates: Map<string, string>;
}

export const MOCK_CATALOGUE_START = "2026-04-01";

/** The seeded categories (migration 010's list), and the units the mock uses. */
const CATEGORY_OF: Readonly<Record<string, string>> = {
  "UPVC PIPE 90 MM 4 KG/CM2 CLASS - 2 IS: 4985": "PVC PIPES",
  "HDPE LATERAL 16 MM 2.5 KG/CM2": "PLAIN LATERAL",
  "INLINE DRIPPER 4 LPH": "DRIP COMPONENTS",
  "SCREEN FILTER 2 INCH 20 M3/HR": "DRIP COMPONENTS",
  "VENTURI INJECTOR 1.5 INCH": "DRIP COMPONENTS",
  "SPRINKLER SET 1 INCH WITH RISER": "SPRINKLER COMPONENTS",
};

const HEAD_UNIT = new Set(["SCREEN FILTER 2 INCH 20 M3/HR", "VENTURI INJECTOR 1.5 INCH"]);

/** The quotation mock marks its second product's figures as stand-ins. */
const PROVISIONAL_INDEX = 1;

function rupees(paise: number): string {
  return (paise / 100).toFixed(2);
}

export function seedProducts(): MockProductRecord[] {
  const priced: MockProductRecord[] = MOCK_PRODUCTS.map((product, index) => {
    const quotationCategory: QuotationCategory = HEAD_UNIT.has(product.name) ? "head" : "field";
    return {
      id: product.id,
      item_code: product.code,
      description: product.name,
      product_category: CATEGORY_OF[product.name] ?? "DRIP COMPONENTS",
      quotation_category: quotationCategory,
      uom: product.uom,
      uom_decimals: product.uomDecimals,
      hsn_code: product.hsn,
      gst_slab: product.slab.toFixed(3),
      mrp: rupees(Math.round(product.rate * 1.25)),
      pack_multiple: product.uom === "MTR" ? "6" : null,
      is_subsidy_eligible: true,
      is_active: true,
      provisional_fields: index === PROVISIONAL_INDEX ? ["hsn_code", "gst_slab"] : [],
    };
  });
  const extra: MockProductRecord[] = [
    {
      id: mockUuid(MOCK_ID_SPACE.quotation, 200),
      item_code: null,
      description: "EMITTING PIPE 16 MM 40 CM SPACING 2 LPH",
      product_category: "EMITTING PIPE",
      quotation_category: "field",
      uom: "MTR",
      uom_decimals: 2,
      hsn_code: null,
      gst_slab: null,
      mrp: null,
      pack_multiple: null,
      is_subsidy_eligible: true,
      is_active: true,
      provisional_fields: [],
    },
    {
      id: mockUuid(MOCK_ID_SPACE.quotation, 201),
      item_code: "PL-2001",
      description: "PVC ELBOW 90 MM",
      product_category: "PVC FITTINGS",
      quotation_category: "both",
      uom: "NOS",
      uom_decimals: 0,
      hsn_code: "3917",
      gst_slab: "18.000",
      mrp: "210.00",
      pack_multiple: "10",
      is_subsidy_eligible: true,
      is_active: true,
      provisional_fields: ["mrp", "pack_multiple"],
    },
    {
      id: mockUuid(MOCK_ID_SPACE.quotation, 202),
      item_code: "PL-2002",
      description: "BALL VALVE 2 INCH (OLD MODEL)",
      product_category: "PVC FITTINGS",
      quotation_category: "head",
      uom: "NOS",
      uom_decimals: 0,
      hsn_code: "8481",
      gst_slab: "18.000",
      mrp: "640.00",
      pack_multiple: null,
      is_subsidy_eligible: false,
      is_active: false,
      provisional_fields: [],
    },
    {
      id: mockUuid(MOCK_ID_SPACE.quotation, 203),
      item_code: null,
      description: "POLYSIL PRODUCT BROCHURE",
      product_category: "Marketing",
      quotation_category: "both",
      uom: "NOS",
      uom_decimals: 0,
      hsn_code: "4911",
      gst_slab: "12.000",
      mrp: null,
      pack_multiple: null,
      is_subsidy_eligible: false,
      is_active: true,
      provisional_fields: [],
    },
  ];
  return [...priced, ...extra];
}

/** Every product's classification history: one row from the catalogue's start. */
export function seedHsnHistory(products: readonly MockProductRecord[]): Map<string, HsnRowWire[]> {
  const history = new Map<string, HsnRowWire[]>();
  for (const [index, product] of products.entries()) {
    history.set(
      product.id,
      product.hsn_code === null
        ? []
        : [
            {
              id: mockUuid(MOCK_ID_SPACE.lookup, 0x500 + index),
              hsn_code: product.hsn_code,
              effective_from: MOCK_CATALOGUE_START,
              effective_to: null,
            },
          ],
    );
  }
  return history;
}

/** The Council's rates the mock knows; a code with none leaves its products' slab a guess. */
export function seedTaxRates(): TaxRateWire[] {
  return [
    ["8421", "18.000"],
    ["8424", "12.000"],
    ["8481", "18.000"],
    ["4911", "12.000"],
  ].map(([hsn, rate], index) => ({
    id: mockUuid(MOCK_ID_SPACE.lookup, 0x600 + index),
    hsn_code: hsn ?? "",
    rate: rate ?? "0",
    effective_from: MOCK_CATALOGUE_START,
    effective_to: null,
    is_active: true,
  }));
}

export function seedPriceLists(products: readonly MockProductRecord[]): MockPriceList[] {
  const gujarat = MOCK_TERRITORIES.find((territory) => territory.level === "state") ?? null;
  const baseRates = new Map(
    MOCK_PRODUCTS.map((product) => [product.id, rupees(product.rate)] as const),
  );
  const oldRates = new Map(
    MOCK_PRODUCTS.map((product) => [product.id, rupees(Math.round(product.rate * 0.94))] as const),
  );
  const dealerRates = new Map(
    MOCK_PRODUCTS.slice(0, 2).map(
      (product) => [product.id, rupees(Math.round(product.rate * 0.9))] as const,
    ),
  );
  const lists: MockPriceList[] = [
    {
      id: mockUuid(MOCK_ID_SPACE.quotation, 2),
      name: "GJ 2026-27",
      state_territory: null,
      channel_tier: null,
      status: "published",
      published_at: "2026-03-28T06:30:00Z",
      effective_from: MOCK_CATALOGUE_START,
      effective_to: null,
      is_active: true,
      is_provisional: true,
      item_count: 0,
      unpriced_count: 0,
      rates: baseRates,
    },
    {
      id: mockUuid(MOCK_ID_SPACE.quotation, 3),
      name: "GJ 2025-26",
      state_territory: null,
      channel_tier: null,
      status: "published",
      published_at: "2025-03-25T06:30:00Z",
      effective_from: "2025-04-01",
      effective_to: MOCK_CATALOGUE_START,
      is_active: true,
      is_provisional: true,
      item_count: 0,
      unpriced_count: 0,
      rates: oldRates,
    },
    {
      id: mockUuid(MOCK_ID_SPACE.quotation, 4),
      name: "Gujarat dealers, November",
      state_territory: gujarat === null ? null : { id: gujarat.id, name: gujarat.name },
      channel_tier: "dealer",
      status: "draft",
      published_at: null,
      effective_from: "2026-11-01",
      effective_to: null,
      is_active: true,
      is_provisional: false,
      item_count: 0,
      unpriced_count: 0,
      rates: dealerRates,
    },
  ];
  return lists.map((list) => withCounts(list, products));
}

/** A list's item and unpriced counts, from its rates and the active catalogue. */
export function withCounts(
  list: MockPriceList,
  products: readonly MockProductRecord[],
): MockPriceList {
  const active = products.filter((product) => product.is_active);
  return {
    ...list,
    item_count: list.rates.size,
    unpriced_count: active.filter((product) => !list.rates.has(product.id)).length,
  };
}
