"use client";

import type * as React from "react";

import { PdfLinkButton } from "@/components/patterns/pdf-link-button";
import { getQuotationPdf } from "@/features/quotations/api/quotations.api";
import type { PdfState } from "@/features/quotations/api/quotations.schemas";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/quotations/components/quotation-pdf-button.tsx",
  dataId: "QUOT-003",
});

export interface QuotationPdfButtonProps {
  quotationId: string;
  pdfState: PdfState;
}

/** QUOT-003 · Opens the quotation's PDF in a new tab, from a fresh signed link. */
export function QuotationPdfButton({
  quotationId,
  pdfState,
}: QuotationPdfButtonProps): React.JSX.Element {
  return (
    <PdfLinkButton
      getLink={() => getQuotationPdf(quotationId)}
      pdfState={pdfState}
      logger={log}
      dataId="QUOT-003"
    />
  );
}
