"use client";

import { ArrowDown01Icon, Download04Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { useAsyncAction } from "@/hooks/use-async-action";
import type { DownloadedFile, ExportFormat } from "@/lib/api/client";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { saveFile } from "@/lib/api/save-file";
import type { DataId } from "@/lib/data-ids";
import type { Logger } from "@/lib/logger";

const FORMAT_LABELS: Readonly<Record<ExportFormat, string>> = {
  xlsx: "Excel",
  csv: "CSV",
  pdf: "PDF",
};

const EXTENSIONS: Readonly<Record<ExportFormat, string>> = {
  xlsx: ".xlsx",
  csv: ".csv",
  pdf: ".pdf",
};

export interface DownloadExcelButtonProps {
  /** Fetches the file for the filters on screen, in the format asked. */
  download: (format: ExportFormat) => Promise<DownloadedFile>;
  /** The Excel file's name when the backend sends none, e.g. "orders.xlsx". */
  fallbackName: string;
  /** What the rows are, plural, for "Too many orders to download". */
  what: string;
  logger: Logger;
  dataId: DataId;
  /** The formats besides Excel (FS-077): CSV for a list; CSV and PDF for a report. */
  otherFormats?: readonly Exclude<ExportFormat, "xlsx">[];
}

/**
 * "Download Excel" for a list: the backend's file of exactly the rows the filters show, every
 * page, saved under the name it gives. Beside it, the same rows as CSV (and a report as PDF,
 * FS-077). More than 5,000 rows is refused (`export_too_large`); the toast says to narrow the
 * filters. A busy PDF maker says to try again in a moment.
 */
export function DownloadExcelButton({
  download,
  fallbackName,
  what,
  logger,
  dataId,
  otherFormats = ["csv"],
}: DownloadExcelButtonProps): React.JSX.Element {
  const run = useAsyncAction({
    action: async (format: ExportFormat) => ({ format, file: await download(format) }),
    logger,
    fn: "handleDownloadExcel",
    dataId,
    onSuccess: ({ format, file }) => {
      saveFile(file, fallbackName.replace(/\.xlsx$/, EXTENSIONS[format]));
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "export_too_large") {
        toast.error(`Too many ${what} to download`, {
          description: "More than 5,000 match. Narrow the filters and try again.",
        });
        return;
      }
      if (isApiError(error) && error.status === 503 && error.code === "busy") {
        toast.error("The PDF maker is busy", {
          description: "Other PDFs are being made. Try again in a moment.",
        });
        return;
      }
      const view = toUserFacingError(error);
      toast.error(view.title, { description: view.description });
    },
  });

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="outline"
        state={run.state}
        loadingLabel="Preparing…"
        successLabel="Downloaded"
        errorLabel="Not downloaded"
        onClick={() => {
          void run.run("xlsx");
        }}
      >
        <Icon icon={Download04Icon} />
        Download Excel
      </Button>
      {otherFormats.length === 0 ? null : (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="outline" size="icon-md" aria-label="Other formats" />}
          >
            <Icon icon={ArrowDown01Icon} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            {otherFormats.map((format) => (
              <DropdownMenuItem
                key={format}
                onClick={() => {
                  void run.run(format);
                }}
              >
                <Icon icon={Download04Icon} />
                Download {FORMAT_LABELS[format]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
