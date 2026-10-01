"use client";

import { Pdf01Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import type { DataId } from "@/lib/data-ids";
import type { Logger } from "@/lib/logger";

/** A signed link to a document's PDF, as the backend hands it out. */
export interface PdfLinkTarget {
  readonly url: string;
  readonly filename: string;
}

export interface PdfLinkButtonProps {
  /** Asks the backend for a fresh signed link. */
  getLink: () => Promise<PdfLinkTarget>;
  /** `ready` enables the button; `pending` says it is being prepared. */
  pdfState: "none" | "pending" | "ready" | "failed";
  logger: Logger;
  dataId: DataId;
  label?: string;
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
 * Opens a document's PDF in a new tab. The backend hands out a signed link that lasts ten
 * minutes, fetched on each click — the file itself is never fetched with the sign-in token.
 * The tab is opened on the click, before the link arrives, so pop-up blockers allow it; if
 * one blocks it anyway, a toast offers the link to open by hand.
 */
export function PdfLinkButton({
  getLink,
  pdfState,
  logger,
  dataId,
  label = "Open PDF",
}: PdfLinkButtonProps): React.JSX.Element {
  const open = useAsyncAction({
    action: async (tab: Window | null) => {
      try {
        const link = await getLink();
        return { link, tab };
      } catch (error) {
        tab?.close();
        throw error;
      }
    },
    logger,
    fn: "handleOpenPdf",
    dataId,
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
      {pdfState === "pending" ? "Preparing PDF…" : label}
    </Button>
  );
}
