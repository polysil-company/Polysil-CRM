import type { WarrantyTermWire } from "@/features/warranty/api/warranty.schemas";

import { MOCK_PRODUCT_CATEGORIES } from "./products";
import { mockUuid } from "./reference";

/** The mock's own id space for warranty terms and categories. */
export const WARRANTY_SPACE = 0x3a12;

/** The product categories a warranty term names: the same rows `GET /lookups/product-categories` lists. */
export const MOCK_WARRANTY_CATEGORIES: readonly { id: string; code: string; name: string }[] =
  MOCK_PRODUCT_CATEGORIES.map((category) => ({
    id: category.id,
    code: category.code,
    name: category.name,
  }));

/** The stand-in until the client answers: 12 months for everything; drip components 24 (a sample). */
export function seedWarrantyTerms(): WarrantyTermWire[] {
  const drip = MOCK_WARRANTY_CATEGORIES.find((item) => item.code === "DRIP COMPONENTS") ?? null;
  return [
    {
      id: mockUuid(WARRANTY_SPACE, 1),
      product_category: null,
      months: 12,
      effective_from: "2026-04-01",
      effective_to: null,
    },
    {
      id: mockUuid(WARRANTY_SPACE, 2),
      product_category: drip,
      months: 24,
      effective_from: "2026-04-01",
      effective_to: null,
    },
  ];
}
