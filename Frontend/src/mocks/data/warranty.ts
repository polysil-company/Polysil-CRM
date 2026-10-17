import type { WarrantyTermWire } from "@/features/warranty/api/warranty.schemas";

import { mockUuid } from "./reference";

/** The mock's own id space for warranty terms and categories. */
export const WARRANTY_SPACE = 0x3a12;

/** The mock's product categories, with the ids a warranty term names. */
export const MOCK_WARRANTY_CATEGORIES: readonly { id: string; code: string; name: string }[] = [
  { id: mockUuid(WARRANTY_SPACE, 101), code: "PVC PIPES", name: "PVC pipes" },
  { id: mockUuid(WARRANTY_SPACE, 102), code: "DRIP COMPONENTS", name: "Drip components" },
];

/** The stand-in until the client answers: 12 months for everything; drip components 24 (a sample). */
export function seedWarrantyTerms(): WarrantyTermWire[] {
  const drip = MOCK_WARRANTY_CATEGORIES[1] ?? null;
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
