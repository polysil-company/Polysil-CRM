"use client";

import { Download04Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useAsyncAction } from "@/hooks/use-async-action";
import type { DownloadedFile } from "@/lib/api/client";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { saveFile } from "@/lib/api/save-file";
import type { DataId } from "@/lib/data-ids";
import type { Logger } from "@/lib/logger";

export interface DownloadFileButtonProps {
  /** Fetches the file; the backend names it. */
  download: () => Promise<DownloadedFile>;
  /** The file's name when the backend sends none, e.g. "application.pdf". */
  fallbackName: string;
  /** What the button says, e.g. "Download PDF". */
  children: React.ReactNode;
  logger: Logger;
  dataId: DataId;
  variant?: "outline" | "ghost" | "primary";
  size?: "sm" | "md";
}

/**
 * A file the backend makes when asked (a printed sheet, a report as PDF), saved under the
 * name it gives. A PDF maker at its limit answers `503 busy`: the toast says to try again in a
 * moment rather than calling it an error.
 */
export function DownloadFileButton({
  download,
  fallbackName,
  children,
  logger,
  dataId,
  variant = "outline",
  size = "md",
}: DownloadFileButtonProps): React.JSX.Element {
  const run = useAsyncAction({
    action: download,
    logger,
    fn: "handleDownloadFile",
    dataId,
    onSuccess: (file) => {
      saveFile(file, fallbackName);
    },
    onError: (error) => {
      toastDownloadError(error);
    },
  });

  return (
    <Button
      variant={variant}
      size={size}
      state={run.state}
      loadingLabel="Preparing…"
      successLabel="Downloaded"
      errorLabel="Not downloaded"
      onClick={() => {
        void run.run();
      }}
    >
      <Icon icon={Download04Icon} />
      {children}
    </Button>
  );
}

/** A download that didn't come, in words: busy is "try again", anything else its own reason. */
export function toastDownloadError(error: unknown): void {
  if (isApiError(error) && error.status === 503 && error.code === "busy") {
    toast.error("The PDF maker is busy", {
      description: "Other PDFs are being made. Try again in a moment.",
    });
    return;
  }
  if (isApiError(error) && error.code === "pdf_unavailable") {
    toast.error("PDFs can't be made just now", {
      description: "Try again later. If it keeps happening, tell the administrator.",
    });
    return;
  }
  const view = toUserFacingError(error);
  toast.error(view.title, { description: view.description });
}
