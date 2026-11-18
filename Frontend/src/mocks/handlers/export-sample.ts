import type { SamplePricing } from "@/features/orders/api/orders.schemas";
import type { QuotationLineWire, TaxTreatment } from "@/features/quotations/api/quotations.schemas";
import { mockDb } from "@/mocks/db";

import { mockSettings } from "./settings";

/**
 * SO-010 · Export and sample orders in the mock (FS-042, `export-sample-orders-contract.md`):
 * the settings that decide them, and how they reprice a line the domestic pricing made.
 */

function choice(key: string): string | null {
  const setting = mockSettings().find((item) => item.key === key);
  return typeof setting?.value === "string" ? setting.value : null;
}

/** A new export's treatment, from `export_tax_treatment`. */
export function exportTreatment(): TaxTreatment {
  return choice("export_tax_treatment") === "igst" ? "export_igst" : "export_lut";
}

/** A new sample's pricing, from `sample_pricing`. */
export function samplePricing(): SamplePricing {
  return choice("sample_pricing") === "charged" ? "charged" : "free";
}

/** The largest sample, in whole rupees of list value. */
export function sampleMaxValue(): number {
  const setting = mockSettings().find((item) => item.key === "sample_max_value");
  return typeof setting?.value === "number" ? setting.value : 50_000;
}

const toPaise = (value: string): number => Math.round(Number(value) * 100);
const fromPaise = (value: number): string => (value / 100).toFixed(2);

/**
 * A domestically priced line, taxed as the document will be: under a LUT every line is at
 * 0 % IGST; with IGST the slab moves to IGST; an export is never intra-state.
 */
export function withTaxTreatment(
  line: QuotationLineWire,
  treatment: TaxTreatment,
): QuotationLineWire {
  if (treatment === "domestic") return line;
  if (treatment === "export_lut") {
    return {
      ...line,
      cgst_rate: "0.000",
      sgst_rate: "0.000",
      igst_rate: "0.000",
      cgst: "0.00",
      sgst: "0.00",
      igst: "0.00",
      total: line.taxable,
    };
  }
  const igst = toPaise(line.cgst) + toPaise(line.sgst) + toPaise(line.igst);
  return {
    ...line,
    cgst_rate: "0.000",
    sgst_rate: "0.000",
    igst_rate: line.gst_slab,
    cgst: "0.00",
    sgst: "0.00",
    igst: fromPaise(igst),
    total: fromPaise(toPaise(line.taxable) + igst),
  };
}

/** A free sample's line: 100 % off, nothing taxable, a total of 0.00. */
export function asFreeSample(line: QuotationLineWire): QuotationLineWire {
  return {
    ...line,
    discount_pct: "100.000",
    discount1_amt: line.gross,
    after_discount1: "0.00",
    discount2_pct: "0.000",
    discount2_amt: "0.00",
    after_discount2: "0.00",
    discount3_pct: "0.000",
    discount3_amt: "0.00",
    discount: line.gross,
    taxable: "0.00",
    cgst: "0.00",
    sgst: "0.00",
    igst: "0.00",
    total: "0.00",
  };
}

/** The list value of lines: their gross before any discount, in whole rupees. */
export function listValue(lines: readonly QuotationLineWire[]): number {
  return lines.reduce((sum, line) => sum + toPaise(line.gross), 0) / 100;
}

/**
 * The ARN of the default registration's LUT covering a day, or null: an export_lut document
 * is zero-rated under it (422 `lut_missing` at submit when there is none).
 */
export function lutArnOn(day: string): string | null {
  const seller = mockDb.sellerGstins.find((item) => item.is_default) ?? mockDb.sellerGstins[0];
  const lut = seller?.luts.find((item) => item.valid_from <= day && day <= item.valid_to);
  if (lut === undefined) return null;
  lut.in_use = true;
  return lut.arn;
}
