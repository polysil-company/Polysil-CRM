import { z } from "zod";

/**
 * MSTR-018 · Our GST registrations and their LUTs (FS-042, `seller-gstins.md`). An export under
 * the LUT setting needs a LUT of the selling registration covering the document's date.
 */

const isoDate = z.iso.date();

const lutWireSchema = z.object({
  id: z.string().min(1),
  arn: z.string(),
  valid_from: isoDate,
  valid_to: isoDate,
  /** A quotation or order carries it, so it can't be removed. */
  in_use: z.boolean(),
});

const sellerGstinWireSchema = z.object({
  id: z.string().min(1),
  gstin: z.string(),
  legal_name: z.string(),
  state_code: z.string(),
  is_default: z.boolean(),
  is_active: z.boolean(),
  /** Newest year first. */
  luts: z.array(lutWireSchema),
});

export type LutWire = z.input<typeof lutWireSchema>;
export type SellerGstinWire = z.input<typeof sellerGstinWireSchema>;

function toLut(wire: z.output<typeof lutWireSchema>): Lut {
  return {
    id: wire.id,
    arn: wire.arn,
    validFrom: wire.valid_from,
    validTo: wire.valid_to,
    inUse: wire.in_use,
  };
}

export interface Lut {
  readonly id: string;
  readonly arn: string;
  readonly validFrom: string;
  readonly validTo: string;
  readonly inUse: boolean;
}

export interface SellerGstin {
  readonly id: string;
  readonly gstin: string;
  readonly legalName: string;
  readonly stateCode: string;
  readonly isDefault: boolean;
  readonly isActive: boolean;
  readonly luts: readonly Lut[];
}

/** `GET /seller-gstins`: `{ data: SellerGstin[] }`. */
export const sellerGstinsSchema = z
  .object({ data: z.array(sellerGstinWireSchema) })
  .transform(({ data }): SellerGstin[] =>
    data.map((row) => ({
      id: row.id,
      gstin: row.gstin,
      legalName: row.legal_name,
      stateCode: row.state_code,
      isDefault: row.is_default,
      isActive: row.is_active,
      luts: row.luts.map(toLut),
    })),
  );

/** `POST /seller-gstins/{id}/luts`: `{ data: Lut }`. */
export const lutSchema = z.object({ data: lutWireSchema }).transform(({ data }) => toLut(data));

/** `POST /seller-gstins/{id}/luts`. */
export interface AddLutRequest {
  readonly arn: string;
  readonly valid_from: string;
  readonly valid_to: string;
}

/** An ARN is 10 to 20 letters and digits. */
export const ARN_PATTERN = /^[A-Za-z0-9]{10,20}$/;
