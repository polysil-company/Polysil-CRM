"use client";

import {
  Delete02Icon,
  File01Icon,
  FileAttachmentIcon,
  Image01Icon,
  Pdf01Icon,
  Upload04Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteDocument, useUploadDocument } from "@/features/documents/api/documents.mutations";
import {
  documentLinkQueryOptions,
  documentsQueryOptions,
  documentTypesQueryOptions,
} from "@/features/documents/api/documents.queries";
import {
  DOCUMENT_CONTENT_TYPES,
  DOCUMENT_MAX_BYTES,
  DOCUMENT_NAME_MAX,
  DOCUMENTS_PER_RECORD,
  type DocumentsScope,
  type RecordDocument,
  type RecordType,
} from "@/features/documents/api/documents.schemas";
import { documentRefusal } from "@/features/documents/lib/document-refusals";
import { useSession } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatFileSize } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/documents/components/record-documents.tsx",
  dataId: "DOC-001",
});

/** What the file picker offers; the backend judges the content again. */
const ACCEPT = [...DOCUMENT_CONTENT_TYPES, ".heic", ".heif"].join(",");

const RECORD_TYPE_LABELS: Readonly<Record<RecordType, string>> = {
  lead: "Lead",
  quotation: "Quotation",
  sales_order: "Order",
  dispatch: "Dispatch",
  payment: "Payment",
  dealer_application: "Dealer application",
};

export interface RecordDocumentsProps {
  scope: DocumentsScope;
  /** Whoever may add to this record (FS-050): the page knows its permissions. */
  canAdd: boolean;
  /** A merged lead or a voided dispatch takes no more documents. */
  closed?: boolean;
  /** "card" on a page; "section" inside a dispatch on the order page. */
  variant?: "card" | "section";
  /** Under the title: what goes here. */
  description?: string;
  /**
   * The record's number, when a page shows more than one record's documents (each dispatch on
   * an order): it names the list and the button, "Documents on D/SO/…", "Attach a file to D/SO/…".
   */
  recordName?: string;
  /** CHNL-007 · What to attach, when the record has none yet and the reader may add. */
  emptyHint?: string;
}

/** A browser that can't name HEIC still sends it: judge by the extension then. */
function acceptedType(file: File): boolean {
  if (DOCUMENT_CONTENT_TYPES.some((type) => type === file.type)) return true;
  return file.type === "" && /\.(heic|heif)$/i.test(file.name);
}

function iconFor(document: RecordDocument): typeof File01Icon {
  if (document.contentType === "application/pdf") return Pdf01Icon;
  if (document.contentType.startsWith("image/")) return Image01Icon;
  return File01Icon;
}

function titleOf(document: RecordDocument): string {
  return document.name ?? document.docTypeLabel;
}

/**
 * DOC-001…003 · The documents on a record — purchase orders, payment slips, invoices, site
 * photos — newest first, each opened through a ten-minute link (a HEIC photo, which browsers
 * can't show, is offered as a download). On a lead, everything made from it shows too, each
 * naming its record. Whoever may add to the record attaches a file with its type, and a name
 * for "Other"; whoever added one, or staff who may add, removes it.
 */
export function RecordDocuments({
  scope,
  canAdd,
  closed = false,
  variant = "card",
  description,
  recordName,
  emptyHint = "No documents yet. Attach the purchase order, a payment slip or a photo.",
}: RecordDocumentsProps): React.JSX.Element {
  const label = recordName === undefined ? "Documents" : `Documents on ${recordName}`;
  const query = useQuery(documentsQueryOptions(scope));
  const session = useSession();
  const meId = session.data?.user.id ?? null;
  const staff = session.data?.userType === "staff";
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<RecordDocument | null>(null);
  const record =
    scope.kind === "lead"
      ? { type: "lead" as const, id: scope.leadId }
      : { type: scope.recordType, id: scope.recordId };
  const own = (query.data ?? []).filter(
    (document) => document.recordType === record.type && document.recordId === record.id,
  );
  const full = own.length >= DOCUMENTS_PER_RECORD;
  const mayAdd = canAdd && !closed;

  /** The uploader, or staff who may add to the record it sits on (this one). */
  const mayRemove = (document: RecordDocument): boolean =>
    !closed &&
    ((meId !== null && document.uploadedBy?.id === meId) ||
      (staff && canAdd && document.recordType === record.type && document.recordId === record.id));

  const addButton = mayAdd ? (
    <Button
      variant="outline"
      size="sm"
      disabled={full}
      aria-label={recordName === undefined ? undefined : `Attach a file to ${recordName}`}
      onClick={() => {
        setAdding(true);
      }}
    >
      <Icon icon={Upload04Icon} />
      Attach a file
    </Button>
  ) : null;

  const list = (
    <QueryView
      query={query}
      pending={<DocumentsSkeleton />}
      isEmpty={(documents) => documents.length === 0}
      empty={
        <p className="text-sm text-muted-foreground">{mayAdd ? emptyHint : "No documents."}</p>
      }
    >
      {(documents) => (
        <div className="flex flex-col gap-2">
          <ul aria-label={label} className="flex flex-col divide-y divide-border">
            {documents.map((document) => (
              <DocumentRow
                key={document.id}
                document={document}
                showRecord={scope.kind === "lead"}
                canRemove={mayRemove(document)}
                onRemove={() => {
                  setRemoving(document);
                }}
              />
            ))}
          </ul>
          {full && mayAdd ? (
            <p className="text-xs text-muted-foreground">
              {`This record has ${String(DOCUMENTS_PER_RECORD)} documents. Remove one to add another.`}
            </p>
          ) : null}
        </div>
      )}
    </QueryView>
  );

  const dialogs = (
    <>
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent size="md">
          {adding ? (
            <AttachForm
              recordType={record.type}
              recordId={record.id}
              existing={query.data ?? []}
              onClose={() => {
                setAdding(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
      <Dialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null);
        }}
      >
        <DialogContent size="sm">
          {removing === null ? null : (
            <RemoveForm
              document={removing}
              onClose={() => {
                setRemoving(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );

  if (variant === "section") {
    return (
      <section aria-label={label} className="flex flex-col gap-2 border-t border-border pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-medium text-foreground">Documents</h4>
          {addButton}
        </div>
        {list}
        {dialogs}
      </section>
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Documents</CardTitle>
          <CardDescription>
            {description ??
              (scope.kind === "lead"
                ? "On this lead and on its quotations, orders and dispatches"
                : "Purchase orders, payment slips, invoices and photos")}
          </CardDescription>
        </div>
        {addButton}
      </CardHeader>
      <CardContent>{list}</CardContent>
      {dialogs}
    </Card>
  );
}

function recordHref(
  document: RecordDocument,
): `/leads/${string}` | `/quotations/${string}` | `/sales-orders/${string}` | null {
  switch (document.recordType) {
    case "lead":
      return `/leads/${document.recordId}`;
    case "quotation":
      return `/quotations/${document.recordId}`;
    case "sales_order":
      return `/sales-orders/${document.recordId}`;
    default:
      return null;
  }
}

function DocumentRow({
  document,
  showRecord,
  canRemove,
  onRemove,
}: {
  document: RecordDocument;
  showRecord: boolean;
  canRemove: boolean;
  onRemove: () => void;
}): React.JSX.Element {
  const link = useQuery(documentLinkQueryOptions(document.id));
  const title = titleOf(document);
  const record = `${RECORD_TYPE_LABELS[document.recordType]}${document.recordLabel === null ? "" : ` ${document.recordLabel}`}`;
  const href = recordHref(document);

  return (
    <li className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
        <Icon icon={iconFor(document)} className="text-muted-foreground" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="truncate text-sm font-medium text-foreground" title={title}>
            {title}
          </span>
          {document.name === null ? null : (
            <Badge variant="neutral" size="sm">
              {document.docTypeLabel}
            </Badge>
          )}
          {showRecord ? (
            href === null ? (
              <Badge variant="outline" size="sm">
                {record}
              </Badge>
            ) : (
              <Link
                href={href}
                className="text-xs text-primary-text underline-offset-4 hover:underline"
              >
                {record}
              </Link>
            )
          ) : null}
        </div>
        <p className="truncate text-xs text-muted-foreground" title={document.filename}>
          {document.filename} · {formatFileSize(document.sizeBytes)}
        </p>
        <p className="text-xs text-muted-foreground">
          {document.uploadedBy === null ? "Added" : `Added by ${document.uploadedBy.name}`}{" "}
          <RelativeDate value={document.uploadedAt} />
        </p>
        {link.isError ? (
          <p className="text-xs text-danger">Can&apos;t open it right now. Try again shortly.</p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {/* Never fetched with the bearer token: the ten-minute link opens in a new tab. */}
        <a
          href={link.data?.url}
          target="_blank"
          rel="noreferrer"
          aria-label={`${document.preview ? "Open" : "Download"} ${title}, ${formatFileSize(document.sizeBytes)}`}
          aria-disabled={link.data === undefined ? true : undefined}
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            link.data === undefined && "pointer-events-none opacity-60",
          )}
          onClick={(event) => {
            if (link.data === undefined) event.preventDefault();
          }}
        >
          {document.preview ? "Open" : "Download"}
        </a>
        {canRemove ? (
          <Button variant="ghost" size="icon-sm" aria-label={`Remove ${title}`} onClick={onRemove}>
            <Icon icon={Delete02Icon} />
          </Button>
        ) : null}
      </div>
    </li>
  );
}

/** DOC-002 · The type, a name for "Other" (a note otherwise) and one file, checked here first. */
function AttachForm({
  recordType,
  recordId,
  existing,
  onClose,
}: {
  recordType: RecordType;
  recordId: string;
  existing: readonly RecordDocument[];
  onClose: () => void;
}): React.JSX.Element {
  const types = useQuery(documentTypesQueryOptions(recordType));
  const upload = useUploadDocument();
  const idempotency = useIdempotencyKey();
  const inputRef = useRef<HTMLInputElement>(null);
  const [docType, setDocType] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<{ message: string | null; name: string | null }>({
    message: null,
    name: null,
  });
  const chosen = (types.data ?? []).find((type) => type.code === docType) ?? null;
  const needsName = chosen?.needsName ?? false;

  const problems = {
    type: docType === null ? "Choose what it is." : null,
    name:
      needsName && name.trim() === ""
        ? "Name the document."
        : name.trim().length > DOCUMENT_NAME_MAX
          ? `At most ${String(DOCUMENT_NAME_MAX)} characters.`
          : null,
    file:
      file === null
        ? "Choose a file."
        : !acceptedType(file)
          ? "Only JPEG, PNG, WebP, HEIC or PDF files."
          : file.size > DOCUMENT_MAX_BYTES
            ? "Files up to 10 MB."
            : file.size === 0
              ? "This file is empty."
              : null,
  };
  const visible = shown
    ? { ...problems, name: refusal.name ?? problems.name }
    : { type: null, name: refusal.name, file: null };
  const blocked = problems.type !== null || problems.name !== null || problems.file !== null;

  const submit = useAsyncAction({
    action: () => {
      const body = {
        recordType,
        recordId,
        docType: docType ?? "",
        name: name.trim() === "" ? null : name.trim(),
      };
      if (file === null) return Promise.reject(new Error("No file chosen"));
      return upload.mutateAsync({
        ...body,
        file,
        idempotencyKey: idempotency.keyFor({ ...body, file: `${file.name}:${String(file.size)}` }),
      });
    },
    logger: log,
    fn: "handleAttachDocument",
    dataId: "DOC-002",
    onSuccess: (document) => {
      idempotency.reset();
      const already = existing.some((item) => item.id === document.id);
      toast.success(already ? "That file is already attached" : "Attached", {
        description: titleOf(document),
      });
      onClose();
    },
    onError: (error) => {
      const view = documentRefusal(error);
      if (view.stale) {
        toast.error(view.message ?? "This record changed");
        onClose();
        return;
      }
      setRefusal({ message: view.message, name: view.name });
    },
  });

  return (
    <form
      noValidate
      aria-label="Attach a file"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal({ message: null, name: null });
        if (blocked) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Attach a file</DialogTitle>
        <DialogDescription>JPEG, PNG, WebP, HEIC or PDF, up to 10 MB.</DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={visible.type === null ? undefined : true}>
          <FieldLabel htmlFor="document-type">What it is</FieldLabel>
          <Select
            items={(types.data ?? []).map((type) => ({ value: type.code, label: type.label }))}
            value={docType}
            onValueChange={(next) => {
              setDocType(next);
            }}
          >
            <SelectTrigger
              id="document-type"
              className="w-full"
              aria-invalid={visible.type === null ? undefined : true}
              aria-describedby={visible.type === null ? undefined : "document-type-error"}
            >
              <SelectValue
                placeholder={
                  types.isPending
                    ? "Loading the types…"
                    : types.isError
                      ? "The types couldn't be loaded"
                      : "Choose a type"
                }
              />
            </SelectTrigger>
            <SelectContent>
              {(types.data ?? []).map((type) => (
                <SelectItem key={type.code} value={type.code}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {types.isError ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="self-start"
              onClick={() => {
                void types.refetch();
              }}
            >
              Load the types again
            </Button>
          ) : null}
          <FieldError id="document-type-error">{visible.type}</FieldError>
        </Field>

        <Field data-invalid={visible.name === null ? undefined : true}>
          <FieldLabel htmlFor="document-name">{needsName ? "Name" : "Note (optional)"}</FieldLabel>
          <Input
            id="document-name"
            autoComplete="off"
            maxLength={DOCUMENT_NAME_MAX}
            value={name}
            aria-invalid={visible.name === null ? undefined : true}
            aria-describedby={visible.name === null ? "document-name-help" : "document-name-error"}
            onChange={(event) => {
              setName(event.target.value);
              setRefusal((current) => ({ ...current, name: null }));
            }}
          />
          {visible.name === null ? (
            <FieldDescription id="document-name-help">
              {needsName
                ? "What this file is, in a few words."
                : "Shown instead of the type, such as “PO 4471 from Patel Farms”."}
            </FieldDescription>
          ) : null}
          <FieldError id="document-name-error">{visible.name}</FieldError>
        </Field>

        <Field data-invalid={visible.file === null ? undefined : true}>
          <FieldLabel htmlFor="document-file-button">File</FieldLabel>
          <input
            ref={inputRef}
            type="file"
            data-testid="document-file-input"
            accept={ACCEPT}
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              event.target.value = "";
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              id="document-file-button"
              type="button"
              variant="outline"
              aria-describedby={visible.file === null ? undefined : "document-file-error"}
              onClick={() => {
                inputRef.current?.click();
              }}
            >
              <Icon icon={FileAttachmentIcon} />
              {file === null ? "Choose a file" : "Choose another"}
            </Button>
            {file === null ? null : (
              <span className="min-w-0 truncate text-sm text-foreground" title={file.name}>
                {file.name} · {formatFileSize(file.size)}
              </span>
            )}
          </div>
          <FieldError id="document-file-error">{visible.file}</FieldError>
        </Field>

        {refusal.message === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal.message}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Attaching…"
          successLabel="Attached"
          errorLabel="Not attached"
        >
          Attach
        </Button>
      </DialogFooter>
    </form>
  );
}

/** DOC-003 · Remove a document; it stays on record for the audit trail. */
function RemoveForm({
  document,
  onClose,
}: {
  document: RecordDocument;
  onClose: () => void;
}): React.JSX.Element {
  const remove = useDeleteDocument();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<string | null>(null);
  const submit = useAsyncAction({
    action: () =>
      remove.mutateAsync({
        documentId: document.id,
        idempotencyKey: idempotency.keyFor({ remove: document.id }),
      }),
    logger: log,
    fn: "handleRemoveDocument",
    dataId: "DOC-003",
    onSuccess: () => {
      toast.success("Document removed", { description: titleOf(document) });
      onClose();
    },
    onError: (error) => {
      const view = documentRefusal(error);
      if (view.stale) {
        toast.error(view.message ?? "This document changed");
        onClose();
        return;
      }
      setRefusal(view.message);
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>Remove this document?</DialogTitle>
        <DialogDescription className="wrap-break-word">
          {titleOf(document)} ({document.filename}). It leaves the list; the record keeps it for the
          audit trail.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          variant="destructive"
          state={submit.state}
          loadingLabel="Removing…"
          successLabel="Removed"
          errorLabel="Not removed"
          onClick={() => {
            setRefusal(null);
            void submit.run();
          }}
        >
          Remove
        </Button>
      </DialogFooter>
    </div>
  );
}

function DocumentsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading documents" className="flex flex-col gap-3">
      {[0, 1].map((index) => (
        <div key={index} className="flex items-center gap-3">
          <Skeleton className="size-8 rounded-md" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-64" />
          </div>
          <Skeleton className="h-8 w-16" />
        </div>
      ))}
    </div>
  );
}
