"use client";

import { Pdf01Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { getQuotationPdf } from "@/features/quotations/api/quotations.api";
import type { PdfState } from "@/features/quotations/api/quotations.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/quotations/components/quotation-pdf-button.tsx",
  dataId: "QUOT-003",
});

export interface QuotationPdfButtonProps {
  quotationId: string;
  pdfState: PdfState;
}

/** What a refusal of the PDF link means to the person who asked. */
function pdfErrorMessage(error: unknown): { title: string; description: string } {
  if (isApiError(error) && error.code === "pdf_pending") {
    return {
      title: "The PDF is still being prepared",
      description: "It is usually ready within a few seconds. Try again shortly.",
    };
  }
  if (isApiError(error) && error.code === "pdf_failed") {
    return { title: "The PDF couldn't be made", description: error.message };
  }
  const view = toUserFacingError(error);
  return { title: view.title, description: view.description };
}

/**
 * QUOT-003 · Opens the quotation's PDF in a new tab. The backend hands out a signed link that
 * lasts ten minutes, fetched on each click — the file itself is never fetched with the
 * sign-in token. The tab is opened on the click, before the link arrives, so pop-up blockers
 * allow it; if one blocks it anyway, a toast offers the link to open by hand.
 */
export function QuotationPdfButton({
  quotationId,
  pdfState,
}: QuotationPdfButtonProps): React.JSX.Element {
  const open = useAsyncAction({
    action: async (tab: Window | null) => {
      try {
        const link = await getQuotationPdf(quotationId);
        return { link, tab };
      } catch (error) {
        tab?.close();
        throw error;
      }
    },
    logger: log,
    fn: "handleOpenPdf",
    dataId: "QUOT-003",
    successMs: 0,
    onSuccess: ({ link, tab }) => {
      if (tab !== null && !tab.closed) {
        tab.location.href = link.url;
        return;
      }
      toast("Your browser blocked the new tab", {
        description: link.filename,
        action: {
          label: "Open PDF",
          onClick: () => {
            window.open(link.url, "_blank", "noopener,noreferrer");
          },
        },
      });
    },
    onError: (error) => {
      const message = pdfErrorMessage(error);
      toast.error(message.title, { description: message.description });
    },
  });

  return (
    <Button
      variant="outline"
      state={open.state}
      loadingLabel="Opening…"
      errorLabel="Not opened"
      disabled={pdfState !== "ready" && open.state === "idle"}
      onClick={() => {
        // Opened now, while the click still counts as the user's; pointed at the PDF below.
        const tab = window.open("", "_blank");
        if (tab !== null) {
          tab.opener = null;
        }
        void open.run(tab);
      }}
    >
      <Icon icon={Pdf01Icon} />
      {pdfState === "pending" ? "Preparing PDF…" : "Open PDF"}
    </Button>
  );
}
