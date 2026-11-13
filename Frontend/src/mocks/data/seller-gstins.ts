import type { SellerGstinWire } from "@/features/products/api/seller-gstins.schemas";

import { MOCK_SELLER } from "./quotations";
import { mockUuid } from "./reference";

/** The mock's own id space for seller registrations and LUTs. */
export const SELLER_GSTIN_SPACE = 0x6577;

/**
 * Two registrations: Gujarat, the default, with this year's LUT (carried by a document) and
 * last year's; Rajasthan, with this year's LUT that no document carries yet, so it can go.
 */
export function seedSellerGstins(): SellerGstinWire[] {
  return [
    {
      id: MOCK_SELLER.id,
      gstin: MOCK_SELLER.gstin,
      legal_name: MOCK_SELLER.legal_name,
      state_code: MOCK_SELLER.state,
      is_default: true,
      is_active: true,
      luts: [
        {
          id: mockUuid(SELLER_GSTIN_SPACE, 11),
          arn: "AD2404260012345",
          valid_from: "2026-04-01",
          valid_to: "2027-03-31",
          in_use: true,
        },
        {
          id: mockUuid(SELLER_GSTIN_SPACE, 12),
          arn: "AD2403250098765",
          valid_from: "2025-04-01",
          valid_to: "2026-03-31",
          in_use: true,
        },
      ],
    },
    {
      id: mockUuid(SELLER_GSTIN_SPACE, 2),
      gstin: "08AAACP1234A1Z9",
      legal_name: MOCK_SELLER.legal_name,
      state_code: "RJ",
      is_default: false,
      is_active: true,
      luts: [
        {
          id: mockUuid(SELLER_GSTIN_SPACE, 21),
          arn: "AD0804260054321",
          valid_from: "2026-04-01",
          valid_to: "2027-03-31",
          in_use: false,
        },
      ],
    },
  ];
}
