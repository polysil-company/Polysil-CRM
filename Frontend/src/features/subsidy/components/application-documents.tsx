"use client";

import {
  CheckmarkCircle02Icon,
  File01Icon,
  Image01Icon,
  Pdf01Icon,
  Upload04Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useUploadApplicationDocument } from "@/features/subsidy/api/subsidy-applications.mutations";
import {
  checklistQueryOptions,
  documentLinkQueryOptions,
} from "@/features/subsidy/api/subsidy-applications.queries";
import {
  APPLICATION_DOCUMENT_MAX_BYTES,
  APPLICATION_DOCUMENT_TYPES,
  APPLICATION_DOCUMENTS_MAX,
  type Application,
  type ApplicationDocument,
  type ChecklistItem,
} from "@/features/subsidy/api/subsidy-applications.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/subsidy/components/application-documents.tsx",
  dataId: "SUBS-007",
});

/** What the file picker offers; the backend judges the content again. */
const ACCEPT = [...APPLICATION_DOCUMENT_TYPES, ".heic", ".heif"].join(",");

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${formatNumber(bytes / (1024 * 1024), 1)} MB`;
  return `${formatNumber(Math.max(1, Math.round(bytes / 1024)))} KB`;
}

/** A browser that can't name HEIC still sends it: judge by the extension then. */
function acceptedType(file: File): boolean {
  if (APPLICATION_DOCUMENT_TYPES.some((type) => type === file.type)) return true;
  return file.type === "" && /\.(heic|heif)$/i.test(file.name);
}

/** The upload refusals the contract names, in words. */
function uploadRefusal(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 413) return "Over 10 MB.";
    if (error.code === "too_many_documents") return "The application has 40 files already.";
    if (error.code === "attachment_type") return "Only PDF, JPEG, PNG, WebP or HEIC.";
    if (error.code === "storage_unavailable" || error.status === 503) {
      return "Files can't be stored right now. Try again later.";
    }
    if (error.code === "status_changed") return "The application has been cancelled.";
  }
  return toUserFacingError(error).title;
}

interface PendingUpload {
  readonly key: string;
  readonly code: string;
  readonly file: File;
  readonly state: "uploading" | "failed";
  readonly message: string | null;
}

/**
 * SUBS-007 · The documents GGRC asks for, as a checklist: each item with its files, opened
 * through a ten-minute link. Whoever may change the application adds files against an item;
 * each is checked here first, then sent on its own, so one failure never loses the others.
 * None is required yet.
 */
export function ApplicationDocuments({
  application,
  canWrite,
}: {
  application: Application;
  canWrite: boolean;
}): React.JSX.Element {
  const checklist = useQuery(checklistQueryOptions(application.id));
  const upload = useUploadApplicationDocument();
  const inputRef = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const mayUpload = canWrite && application.status !== "cancelled";
  const count = (checklist.data ?? []).reduce((sum, item) => sum + item.files.length, 0);
  const room =
    APPLICATION_DOCUMENTS_MAX - count - pending.filter((item) => item.state === "uploading").length;

  const canAdd = mayUpload && room > 0;

  const send = async (item: PendingUpload): Promise<void> => {
    setPending((list) =>
      list.map((entry) =>
        entry.key === item.key ? { ...entry, state: "uploading", message: null } : entry,
      ),
    );
    try {
      await log.trace("handleUploadDocument", () =>
        upload.mutateAsync({
          applicationId: application.id,
          documentType: item.code,
          file: item.file,
          idempotencyKey: item.key,
        }),
      );
      setPending((list) => list.filter((entry) => entry.key !== item.key));
    } catch (error) {
      setPending((list) =>
        list.map((entry) =>
          entry.key === item.key
            ? { ...entry, state: "failed", message: uploadRefusal(error) }
            : entry,
        ),
      );
    }
  };

  const onFiles = (code: string, files: FileList | null): void => {
    if (files === null || files.length === 0) return;
    const refused: string[] = [];
    const accepted: PendingUpload[] = [];
    for (const file of Array.from(files)) {
      if (!acceptedType(file)) refused.push(`${file.name}: not a PDF or a photo`);
      else if (file.size > APPLICATION_DOCUMENT_MAX_BYTES) refused.push(`${file.name}: over 10 MB`);
      else if (file.size === 0) refused.push(`${file.name}: empty`);
      else if (accepted.length >= room) refused.push(`${file.name}: the application has 40 files`);
      else accepted.push({ key: createRequestId(), code, file, state: "uploading", message: null });
    }
    if (refused.length > 0) {
      toast.error(
        refused.length === 1
          ? "One file wasn't added"
          : `${String(refused.length)} files weren't added`,
        { description: refused.join(" · ") },
      );
    }
    setPending((list) => [...list, ...accepted]);
    for (const item of accepted) void send(item);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Documents</CardTitle>
          <CardDescription>
            {checklist.data === undefined
              ? "The enclosures GGRC asks for."
              : `${String(application.documents.uploaded)} of ${String(application.documents.listed)} items have a file · ${String(count)} of ${String(APPLICATION_DOCUMENTS_MAX)} files`}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {mayUpload ? (
          <input
            ref={inputRef}
            type="file"
            data-testid="application-file-input"
            multiple
            accept={ACCEPT}
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              if (target !== null) onFiles(target, event.target.files);
              event.target.value = "";
            }}
          />
        ) : null}
        {checklist.status === "pending" ? (
          <div className="flex flex-col gap-2" aria-hidden>
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-10 w-full" />
            ))}
          </div>
        ) : checklist.status === "error" ? (
          <ErrorState
            error={checklist.error}
            onRetry={() => {
              void checklist.refetch();
            }}
          />
        ) : (
          <ul aria-label="Document checklist" className="flex flex-col divide-y divide-border">
            {checklist.data
              .filter((item) => item.active || item.files.length > 0)
              .map((item) => (
                <ChecklistRow
                  key={item.code}
                  applicationId={application.id}
                  item={item}
                  pending={pending.filter((entry) => entry.code === item.code)}
                  canAdd={canAdd}
                  onAdd={() => {
                    setTarget(item.code);
                    inputRef.current?.click();
                  }}
                  onRetry={(entry) => {
                    void send(entry);
                  }}
                  onDismiss={(entry) => {
                    setPending((list) => list.filter((other) => other.key !== entry.key));
                  }}
                />
              ))}
          </ul>
        )}
        {mayUpload ? (
          <p className="text-xs text-muted-foreground">
            {room <= 0
              ? "This application has 40 files: no more can be added."
              : "PDF, JPEG, PNG, WebP or HEIC, up to 10 MB each. None is required yet."}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ChecklistRow({
  applicationId,
  item,
  pending,
  canAdd,
  onAdd,
  onRetry,
  onDismiss,
}: {
  applicationId: string;
  item: ChecklistItem;
  pending: readonly PendingUpload[];
  canAdd: boolean;
  onAdd: () => void;
  onRetry: (entry: PendingUpload) => void;
  onDismiss: (entry: PendingUpload) => void;
}): React.JSX.Element {
  const has = item.files.length > 0;
  return (
    <li aria-label={item.name} className="flex flex-col gap-2 py-2.5">
      <div className="flex items-start gap-2.5">
        <Icon
          icon={has ? CheckmarkCircle02Icon : File01Icon}
          className={cn("mt-0.5 shrink-0", has ? "text-success" : "text-subtle-foreground")}
        />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <p className="text-sm text-foreground">{item.name}</p>
          <p className="text-xs text-muted-foreground">
            {has
              ? item.files.length === 1
                ? "1 file"
                : `${String(item.files.length)} files`
              : "No file yet"}
          </p>
        </div>
        {canAdd ? (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Add a file to ${item.name}`}
            onClick={onAdd}
          >
            <Icon icon={Upload04Icon} />
            Add
          </Button>
        ) : null}
      </div>
      {has || pending.length > 0 ? (
        <ul className="flex flex-wrap gap-2 pl-7">
          {item.files.map((file) => (
            <DocumentChip key={file.id} applicationId={applicationId} document={file} />
          ))}
          {pending.map((entry) => (
            <li
              key={entry.key}
              aria-busy={entry.state === "uploading" || undefined}
              className="flex max-w-full flex-col gap-1 rounded-md border border-dashed border-border px-2.5 py-1.5 text-xs"
            >
              <span className="truncate text-foreground">{entry.file.name}</span>
              {entry.state === "uploading" ? (
                <span role="status" className="text-muted-foreground">
                  Uploading…
                </span>
              ) : (
                <>
                  <span role="alert" className="text-danger">
                    {entry.message}
                  </span>
                  <span className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        onRetry(entry);
                      }}
                    >
                      Try again
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        onDismiss(entry);
                      }}
                    >
                      Dismiss
                    </Button>
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function DocumentChip({
  applicationId,
  document,
}: {
  applicationId: string;
  document: ApplicationDocument;
}): React.JSX.Element {
  const link = useQuery(documentLinkQueryOptions(applicationId, document.id));
  const icon =
    document.contentType === "application/pdf"
      ? Pdf01Icon
      : document.contentType.startsWith("image/")
        ? Image01Icon
        : File01Icon;
  return (
    <li className="max-w-full">
      <a
        href={link.data?.url}
        target="_blank"
        rel="noreferrer"
        aria-label={`Open ${document.filename}, ${formatSize(document.sizeBytes)}`}
        aria-disabled={link.data === undefined ? true : undefined}
        className="flex max-w-full items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-foreground transition-colors duration-fast hover:bg-accent"
        onClick={(event) => {
          if (link.data === undefined) event.preventDefault();
        }}
      >
        <Icon icon={icon} size="sm" className="shrink-0 text-muted-foreground" />
        <span className="truncate">{document.filename}</span>
        <span className="shrink-0 text-muted-foreground">{formatSize(document.sizeBytes)}</span>
      </a>
      {link.isError ? (
        <p className="mt-0.5 text-xs text-danger">Can&apos;t open it right now.</p>
      ) : null}
    </li>
  );
}
