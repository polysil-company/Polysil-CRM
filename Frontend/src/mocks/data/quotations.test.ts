import { describe, expect, it } from "vitest";

import {
  quotationResponseSchema,
  quotationSummarySchema,
} from "@/features/quotations/api/quotations.schemas";

import { generateLeads } from "./leads";
import { generateQuotations, toQuotationSummary } from "./quotations";

/** A decimal string in whole paise, for exact comparisons. */
function paise(amount: string): number {
  return Math.round(Number(amount) * 100);
}

describe("[QUOT-002] mock quotations", () => {
  const leads = generateLeads();
  const quotations = generateQuotations(leads);

  it("match the backend's contract, as documents and as list rows", () => {
    expect(quotations.length).toBeGreaterThan(10);
    for (const quotation of quotations) {
      expect(quotationResponseSchema.safeParse({ data: quotation }).success, quotation.id).toBe(
        true,
      );
      expect(
        quotationSummarySchema.safeParse(toQuotationSummary(quotation)).success,
        quotation.id,
      ).toBe(true);
    }
  });

  it("add up to the paisa: each tier on the running balance, tax on the taxable value", () => {
    for (const quotation of quotations) {
      for (const line of quotation.lines) {
        expect(paise(line.gross) - paise(line.discount1_amt)).toBe(paise(line.after_discount1));
        expect(paise(line.after_discount1) - paise(line.discount2_amt)).toBe(
          paise(line.after_discount2),
        );
        expect(paise(line.after_discount2) - paise(line.discount3_amt)).toBe(paise(line.taxable));
        expect(paise(line.taxable) + paise(line.cgst) + paise(line.sgst) + paise(line.igst)).toBe(
          paise(line.total),
        );
      }
      const sum = quotation.lines.reduce((total, line) => total + paise(line.total), 0);
      expect(paise(quotation.totals.total), quotation.id).toBe(sum);
    }
  });

  it("give a draft no number, and a revision its predecessor's number with the next version", () => {
    for (const quotation of quotations.filter((item) => item.status === "draft")) {
      expect(quotation.quote_no).toBeNull();
      expect(quotation.share_url).toBeNull();
    }
    const revised = quotations.find((item) => item.supersedes !== null);
    const original = quotations.find((item) => item.id === revised?.supersedes?.id);
    expect(revised?.version).toBe(2);
    expect(original?.superseded_by).toEqual({ id: revised?.id, version: 2 });
    expect(original?.quote_no).toBe(revised?.quote_no);
  });
});
