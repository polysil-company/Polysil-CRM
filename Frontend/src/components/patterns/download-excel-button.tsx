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

export interface DownloadExcelButtonProps {
  /** Fetches the workbook for the filters on screen. */
  download: () => Promise<DownloadedFile>;
  /** The file's name when the backend sends none, e.g. "orders.xlsx". */
  fallbackName: string;
  /** What the rows are, plural, for "Too many orders to download". */
  what: string;
  logger: Logger;
  dataId: DataId;
}

/**
 * "Download Excel" for a list: the backend's workbook of exactly the rows the filters show,
 * every page, saved under the name it gives. More than 5,000 rows is refused
 * (`export_too_large`); the toast says to narrow the filters.
 */
export function DownloadExcelButton({
  download,
  fallbackName,
  what,
  logger,
  dataId,
}: DownloadExcelButtonProps): React.JSX.Element {
  const run = useAsyncAction({
    action: download,
    logger,
    fn: "handleDownloadExcel",
    dataId,
    onSuccess: (file) => {
      saveFile(file, fallbackName);
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "export_too_large") {
        toast.error(`Too many ${what} to download`, {
          description: "More than 5,000 match. Narrow the filters and try again.",
        });
        return;
      }
      const view = toUserFacingError(error);
      toast.error(view.title, { description: view.description });
    },
  });

  return (
    <Button
      variant="outline"
      state={run.state}
      loadingLabel="Preparing…"
      successLabel="Downloaded"
      errorLabel="Not downloaded"
      onClick={() => {
        void run.run();
      }}
    >
      <Icon icon={Download04Icon} />
      Download Excel
    </Button>
  );
}
