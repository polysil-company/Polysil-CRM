import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import type { DownloadedFile } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import { DownloadFileButton } from "./download-file-button";

const log = createLogger({
  file: "components/patterns/download-file-button.stories.tsx",
  dataId: "APP-001",
});

function saved(): Promise<DownloadedFile> {
  return Promise.resolve({
    blob: new Blob(["%PDF-1.4"], { type: "application/pdf" }),
    filename: "application.pdf",
  });
}

function busy(): Promise<DownloadedFile> {
  return Promise.reject(
    new ApiError({
      kind: "http",
      message: "Other PDFs are being made.",
      dataId: "APP-001",
      requestId: "3f1c2a90-0000-4000-8000-000000000503",
      method: "GET",
      path: "/dealer-applications/form.pdf",
      status: 503,
      code: "busy",
    }),
  );
}

const meta = {
  title: "Patterns/DownloadFileButton",
  component: DownloadFileButton,
  args: {
    children: "Download PDF",
    fallbackName: "application.pdf",
    logger: log,
    dataId: "APP-001",
    download: saved,
  },
} satisfies Meta<typeof DownloadFileButton>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Press it: "Preparing…", then the file is saved under the backend's name. */
export const Default: Story = {};

/** As a quiet action beside others. */
export const Ghost: Story = { args: { variant: "ghost", size: "sm", children: "Blank form" } };

/** The PDF maker is at its limit: a toast says to try again in a moment. */
export const Busy: Story = { args: { download: busy } };
