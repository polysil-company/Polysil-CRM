"use client";

import {
  Attachment01Icon,
  Delete02Icon,
  File01Icon,
  Image01Icon,
  Pdf01Icon,
  Upload04Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Icon } from "@/components/ui/icon";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDeleteAttachment,
  useUploadAttachment,
} from "@/features/complaints/api/complaints.mutations";
import {
  attachmentLinkQueryOptions,
  complaintStatsQueryOptions,
} from "@/features/complaints/api/complaints.queries";
import {
  ATTACHMENT_KINDS,
  COMPLAINT_ATTACHMENT_MAX_BYTES,
  COMPLAINT_ATTACHMENT_TYPES,
  COMPLAINT_ATTACHMENTS_MAX,
  type AttachmentKind,
  type Complaint,
  type ComplaintAttachment,
} from "@/features/complaints/api/complaints.schemas";
import { complaintRefusal } from "@/features/complaints/lib/complaint-labels";
import { useSession } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { createRequestId } from "@/lib/api/request-id";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { Refusal } from "./complaint-dialog-parts";

const log = createLogger({
  file: "features/complaints/components/attachments-card.tsx",
  dataId: "CMPL-006",
});

export const ATTACHMENT_KIND_LABELS: Readonly<Record<AttachmentKind, string>> = {
  photo: "Photo",
  document: "Document",
  challan: "Challan",
};

/** What the file picker offers; the backend judges the content again. */
const ACCEPT = [...COMPLAINT_ATTACHMENT_TYPES, ".heic", ".heif"].join(",");

/** "2.4 MB", "640 KB". */
function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${formatNumber(bytes / (1024 * 1024), 1)} MB`;
  return `${formatNumber(Math.max(1, Math.round(bytes / 1024)))} KB`;
}

/** A browser that can't name HEIC still sends it: judge by the extension then. */
function acceptedType(file: File): boolean {
  if (COMPLAINT_ATTACHMENT_TYPES.some((type) => type === file.type)) return true;
  return file.type === "" && /\.(heic|heif)$/i.test(file.name);
}

/** One file on its way up, or one that failed and can be tried again. */
interface PendingUpload {
  readonly key: string;
  readonly file: File;
  readonly kind: AttachmentKind;
  readonly state: "uploading" | "failed";
  readonly message: string | null;
}

/**
 * CMPL-006 · The complaint's files: photos, documents and the challan. Pictures show as
 * thumbnails from a ten-minute link; HEIC and PDF show as files to open. Whoever may add
 * files picks a kind and one or more files; each is checked here for size and type first,
 * then sent on its own, so one failure never loses the others.
 */
export function AttachmentsCard({ complaint }: { complaint: Complaint }): React.JSX.Element {
  const stats = useQuery(complaintStatsQueryOptions());
  const session = useSession();
  const storageReady = stats.data?.storageAvailable ?? true;
  const canUpload = complaint.can.upload && storageReady;
  const meId = session.data?.user.id ?? null;
  const [kind, setKind] = useState<AttachmentKind>("photo");
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const [removing, setRemoving] = useState<ComplaintAttachment | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const kindId = useId();
  const upload = useUploadAttachment();
  const count = complaint.attachments.length;
  const room =
    COMPLAINT_ATTACHMENTS_MAX - count - pending.filter((item) => item.state === "uploading").length;

  /** In a draft, whoever added it or an editor; after submit, only whoever added it. */
  const mayRemove = (attachment: ComplaintAttachment): boolean => {
    if (!complaint.can.upload) return false;
    return complaint.status === "draft" || attachment.uploadedBy?.id === meId;
  };

  const send = async (item: PendingUpload): Promise<void> => {
    setPending((list) =>
      list.map((entry) =>
        entry.key === item.key ? { ...entry, state: "uploading", message: null } : entry,
      ),
    );
    try {
      await log.trace("handleUploadAttachment", () =>
        upload.mutateAsync({
          complaintId: complaint.id,
          file: item.file,
          kind: item.kind,
          idempotencyKey: item.key,
        }),
      );
      setPending((list) => list.filter((entry) => entry.key !== item.key));
    } catch (error) {
      const view = complaintRefusal(error);
      setPending((list) =>
        list.map((entry) =>
          entry.key === item.key
            ? { ...entry, state: "failed", message: `${view.title}. ${view.message}` }
            : entry,
        ),
      );
    }
  };

  const onFiles = (files: FileList | null): void => {
    if (files === null || files.length === 0) return;
    const chosen = Array.from(files);
    const refused: string[] = [];
    const accepted: PendingUpload[] = [];
    for (const file of chosen) {
      if (!acceptedType(file)) refused.push(`${file.name}: not a photo or a PDF`);
      else if (file.size > COMPLAINT_ATTACHMENT_MAX_BYTES) refused.push(`${file.name}: over 10 MB`);
      else if (file.size === 0) refused.push(`${file.name}: empty`);
      else if (accepted.length >= room) refused.push(`${file.name}: the complaint has 10 files`);
      else accepted.push({ key: createRequestId(), file, kind, state: "uploading", message: null });
    }
    if (refused.length > 0) {
      toast.error(
        refused.length === 1
          ? "One file wasn't added"
          : `${String(refused.length)} files weren't added`,
        {
          description: refused.join(" · "),
        },
      );
    }
    setPending((list) => [...list, ...accepted]);
    for (const item of accepted) void send(item);
  };

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <CardTitle level={3}>Files</CardTitle>
          <CardDescription>
            {count === 0
              ? "Photos of the defect, documents and the challan."
              : `${String(count)} of ${String(COMPLAINT_ATTACHMENTS_MAX)}`}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!storageReady && complaint.can.upload ? (
          <p role="note" className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
            File storage isn&apos;t set up yet, so files can&apos;t be added. Ask the administrator.
          </p>
        ) : null}

        {count === 0 && pending.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {canUpload ? "No files yet. Add photos of the defect first." : "No files."}
          </p>
        ) : (
          <ul aria-label="Files" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {complaint.attachments.map((attachment) => (
              <AttachmentTile
                key={attachment.id}
                complaintId={complaint.id}
                attachment={attachment}
                canRemove={mayRemove(attachment)}
                onRemove={() => {
                  setRemoving(attachment);
                }}
              />
            ))}
            {pending.map((item) => (
              <PendingTile
                key={item.key}
                item={item}
                onRetry={() => {
                  void send(item);
                }}
                onDismiss={() => {
                  setPending((list) => list.filter((entry) => entry.key !== item.key));
                }}
              />
            ))}
          </ul>
        )}

        {canUpload ? (
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <label htmlFor={kindId} className="text-xs text-muted-foreground">
                Kind
              </label>
              <Select
                items={ATTACHMENT_KINDS.map((value) => ({
                  value,
                  label: ATTACHMENT_KIND_LABELS[value],
                }))}
                value={kind}
                onValueChange={(next) => {
                  if (next !== null) setKind(next);
                }}
              >
                <SelectTrigger id={kindId} className="w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ATTACHMENT_KINDS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {ATTACHMENT_KIND_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <input
              ref={inputRef}
              type="file"
              data-testid="complaint-file-input"
              multiple
              accept={ACCEPT}
              className="sr-only"
              tabIndex={-1}
              aria-hidden="true"
              onChange={(event) => {
                onFiles(event.target.files);
                event.target.value = "";
              }}
            />
            <Button
              variant="outline"
              disabled={room <= 0}
              aria-describedby="complaint-files-hint"
              onClick={() => {
                inputRef.current?.click();
              }}
            >
              <Icon icon={Upload04Icon} />
              Add files
            </Button>
            <p id="complaint-files-hint" className="w-full text-xs text-muted-foreground">
              {room <= 0
                ? "This complaint has 10 files. Remove one to add another."
                : "JPEG, PNG, WebP, HEIC or PDF, up to 10 MB each."}
            </p>
          </div>
        ) : null}
      </CardContent>

      <Dialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null);
        }}
      >
        <DialogContent size="sm">
          {removing === null ? null : (
            <RemoveForm
              complaintId={complaint.id}
              attachment={removing}
              onClose={() => {
                setRemoving(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function kindIcon(attachment: ComplaintAttachment): typeof File01Icon {
  if (attachment.contentType === "application/pdf") return Pdf01Icon;
  if (attachment.contentType.startsWith("image/")) return Image01Icon;
  return File01Icon;
}

function AttachmentTile({
  complaintId,
  attachment,
  canRemove,
  onRemove,
}: {
  complaintId: string;
  attachment: ComplaintAttachment;
  canRemove: boolean;
  onRemove: () => void;
}): React.JSX.Element {
  const picture = attachment.preview && attachment.contentType.startsWith("image/");
  const link = useQuery(attachmentLinkQueryOptions(complaintId, attachment.id));
  const label = `${ATTACHMENT_KIND_LABELS[attachment.kind]}: ${attachment.filename}`;

  return (
    <li className="group relative flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
      <a
        href={link.data?.url}
        target="_blank"
        rel="noreferrer"
        aria-label={`Open ${label}, ${formatSize(attachment.sizeBytes)}`}
        aria-disabled={link.data === undefined ? true : undefined}
        className="flex aspect-4/3 items-center justify-center bg-muted focus-ring-inset"
        onClick={(event) => {
          if (link.data === undefined) event.preventDefault();
        }}
      >
        {picture && link.data !== undefined ? (
          // eslint-disable-next-line @next/next/no-img-element -- a ten-minute signed link from the file store; next/image would cache it past expiry
          <img src={link.data.url} alt="" loading="lazy" className="size-full object-cover" />
        ) : picture && link.isPending ? (
          <Skeleton className="size-full rounded-none" />
        ) : (
          <Icon icon={kindIcon(attachment)} size="lg" className="text-muted-foreground" />
        )}
      </a>
      <div className="flex min-w-0 flex-col gap-0.5 p-2">
        <p className="truncate text-xs font-medium text-foreground" title={attachment.filename}>
          {attachment.filename}
        </p>
        <p className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          <Badge variant="neutral" size="sm">
            {ATTACHMENT_KIND_LABELS[attachment.kind]}
          </Badge>
          {formatSize(attachment.sizeBytes)} · <RelativeDate value={attachment.uploadedAt} />
        </p>
        {link.isError ? <p className="text-xs text-danger">Can&apos;t open it right now.</p> : null}
      </div>
      {canRemove ? (
        <Button
          variant="secondary"
          size="icon-sm"
          aria-label={`Remove ${label}`}
          className="absolute top-1.5 right-1.5"
          onClick={onRemove}
        >
          <Icon icon={Delete02Icon} />
        </Button>
      ) : null}
    </li>
  );
}

function PendingTile({
  item,
  onRetry,
  onDismiss,
}: {
  item: PendingUpload;
  onRetry: () => void;
  onDismiss: () => void;
}): React.JSX.Element {
  const failed = item.state === "failed";
  return (
    <li
      aria-busy={failed ? undefined : true}
      className="flex min-w-0 flex-col overflow-hidden rounded-lg border border-dashed border-border"
    >
      <div className="flex aspect-4/3 items-center justify-center bg-muted">
        {failed ? (
          <Icon icon={Attachment01Icon} size="lg" className="text-danger" />
        ) : (
          <Skeleton className="size-full rounded-none" />
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-1 p-2">
        <p className="truncate text-xs font-medium text-foreground" title={item.file.name}>
          {item.file.name}
        </p>
        {failed ? (
          <>
            <p role="alert" className="text-xs text-danger">
              {item.message}
            </p>
            <div className="flex gap-1">
              <Button size="sm" variant="outline" onClick={onRetry}>
                Try again
              </Button>
              <Button size="sm" variant="ghost" onClick={onDismiss}>
                Dismiss
              </Button>
            </div>
          </>
        ) : (
          <p role="status" className="text-xs text-muted-foreground">
            Uploading…
          </p>
        )}
      </div>
    </li>
  );
}

function RemoveForm({
  complaintId,
  attachment,
  onClose,
}: {
  complaintId: string;
  attachment: ComplaintAttachment;
  onClose: () => void;
}): React.JSX.Element {
  const remove = useDeleteAttachment();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const submit = useAsyncAction({
    action: () =>
      remove.mutateAsync({
        complaintId,
        attachmentId: attachment.id,
        idempotencyKey: idempotency.keyFor({ remove: attachment.id }),
      }),
    logger: log,
    fn: "handleRemoveAttachment",
    dataId: "CMPL-006",
    onSuccess: () => {
      toast.success("File removed", { description: attachment.filename });
      onClose();
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      setRefusal({ title: view.title, message: view.message });
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>Remove this file?</DialogTitle>
        <DialogDescription className="wrap-break-word">{attachment.filename}</DialogDescription>
      </DialogHeader>
      <DialogBody>
        <Refusal refusal={refusal} />
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
