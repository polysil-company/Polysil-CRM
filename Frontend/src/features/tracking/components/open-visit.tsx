"use client";

import { Camera01Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import { useRef, useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Notice } from "@/components/patterns/notice";
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
import { Field, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import {
  VISIT_OUTCOMES,
  type Visit,
  type VisitOutcome,
} from "@/features/tracking/api/tracking.schemas";
import { getVisitPhotoLink } from "@/features/tracking/api/visits.api";
import { useCheckOut, useUploadVisitPhoto } from "@/features/tracking/api/visits.mutations";
import {
  VISIT_PHOTO_MAX,
  VISIT_PHOTO_MAX_BYTES,
  VISIT_PHOTO_TYPES,
  type VisitPhoto,
} from "@/features/tracking/api/visits.schemas";
import { useBrowserFix } from "@/features/tracking/hooks/use-browser-fix";
import { VISIT_OUTCOME_LABELS } from "@/features/tracking/lib/tracking-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { formatNumber, formatTime } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { FixPanel } from "./fix-panel";

const log = createLogger({
  file: "features/tracking/components/open-visit.tsx",
  dataId: "TRK-004",
});

/** Why a photo can't be added, in words, before or after sending it. */
export function photoProblem(file: {
  readonly size: number;
  readonly type: string;
}): string | null {
  if (!VISIT_PHOTO_TYPES.some((type) => type === file.type)) {
    return "Choose a JPEG, PNG, WebP or HEIC photo.";
  }
  if (file.size > VISIT_PHOTO_MAX_BYTES) return "That photo is over 10 MB.";
  return null;
}

function photoRefusal(error: unknown): string | null {
  if (!isApiError(error)) return null;
  if (error.code === "photo_limit") return `A visit takes up to ${String(VISIT_PHOTO_MAX)} photos.`;
  if (error.code === "photo_window_closed") {
    return "Photos are taken until 24 hours after check-in.";
  }
  if (error.status === 413) return "That photo is over 10 MB.";
  return null;
}

/**
 * TRK-004 · The visit the user is checked in at: since when, its photos (up to three, from the
 * camera on a phone), and **Check out** with an outcome and the location.
 */
export function OpenVisitCard({
  visit,
  photoRequired,
}: {
  visit: Visit;
  photoRequired: boolean;
}): React.JSX.Element {
  const [photos, setPhotos] = useState<VisitPhoto[]>([]);
  const [checkingOut, setCheckingOut] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const upload = useUploadVisitPhoto();
  const full = visit.photoCount >= VISIT_PHOTO_MAX;

  const send = useAsyncAction({
    action: (file: Blob & { readonly name: string }) =>
      upload.mutateAsync({ visitId: visit.id, file, idempotencyKey: createRequestId() }),
    logger: log,
    fn: "handleAddPhoto",
    dataId: "TRK-004",
    onSuccess: (photo) => {
      setPhotos((before) => [...before, photo]);
      toast.success("Photo added");
    },
    onError: (error) => {
      toast.error("Photo not added", {
        description: photoRefusal(error) ?? toUserFacingError(error).description,
      });
    },
  });

  const openPhoto = async (photoId: string): Promise<void> => {
    try {
      const link = await getVisitPhotoLink(visit.id, photoId);
      window.open(link.url, "_blank", "noopener,noreferrer");
    } catch (error) {
      toast.error("Photo couldn't be opened", {
        description: toUserFacingError(error).description,
      });
    }
  };

  return (
    <Card className="border-success/40">
      <CardHeader className="flex-wrap">
        <div className="flex min-w-0 flex-col gap-0.5">
          <CardTitle level={3} className="flex flex-wrap items-center gap-2">
            Checked in
            <Badge variant="success" size="sm" dot>
              Open
            </Badge>
          </CardTitle>
          <CardDescription>
            {visit.lead === null ? (
              visit.label
            ) : (
              <Link
                href={`/leads/${visit.lead.id}`}
                className="font-mono text-primary-text underline-offset-4 hover:underline"
              >
                {visit.label}
              </Link>
            )}{" "}
            · since {formatTime(visit.checkinAt)} (<RelativeDate value={visit.checkinAt} />)
          </CardDescription>
        </div>
        <Button
          onClick={() => {
            setCheckingOut(true);
          }}
        >
          Check out
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-foreground tabular-nums">
            {formatNumber(visit.photoCount)} of {formatNumber(VISIT_PHOTO_MAX)} photos
          </span>
          <input
            ref={input}
            type="file"
            accept={VISIT_PHOTO_TYPES.join(",")}
            capture="environment"
            className="sr-only"
            aria-label="Choose a photo"
            tabIndex={-1}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file === undefined) return;
              const problem = photoProblem(file);
              if (problem !== null) {
                toast.error("Photo not added", { description: problem });
                return;
              }
              void send.run(file);
            }}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={full}
            state={send.state}
            loadingLabel="Uploading…"
            successLabel="Added"
            errorLabel="Not added"
            onClick={() => {
              input.current?.click();
            }}
          >
            <Icon icon={Camera01Icon} />
            Add photo
          </Button>
        </div>
        {photos.length === 0 ? null : (
          <ul aria-label="Photos added" className="flex flex-wrap gap-2">
            {photos.map((photo, index) => (
              <li key={photo.id}>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    void openPhoto(photo.id);
                  }}
                >
                  Photo {formatNumber(index + 1)}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {photoRequired && visit.photoCount === 0 ? (
          <p className="text-xs text-muted-foreground">A photo is needed before you check out.</p>
        ) : null}
      </CardContent>

      <Dialog open={checkingOut} onOpenChange={setCheckingOut}>
        <DialogContent size="sm">
          {checkingOut ? (
            <CheckOutForm
              visit={visit}
              photoRequired={photoRequired}
              onDone={() => {
                setCheckingOut(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/** TRK-004 · Close the visit: what came of it, a note, and where the user is now. */
export function CheckOutForm({
  visit,
  photoRequired,
  onDone,
}: {
  visit: Visit;
  photoRequired: boolean;
  onDone: () => void;
}): React.JSX.Element {
  const [outcome, setOutcome] = useState<VisitOutcome | null>(null);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const { state: fix, locate } = useBrowserFix({ autoWhenAllowed: true });
  const mutation = useCheckOut();
  const needsPhoto = photoRequired && visit.photoCount === 0;

  const save = useAsyncAction({
    action: () => {
      if (fix.status !== "ready" || outcome === null) throw new Error("Not ready");
      return mutation.mutateAsync({
        visitId: visit.id,
        body: {
          at: new Date().toISOString(),
          sent_at: new Date().toISOString(),
          lat: fix.fix.lat,
          lng: fix.fix.lng,
          accuracy_m: fix.fix.accuracyM,
          outcome,
          note: note.trim() === "" ? null : note.trim(),
        },
        // A new key each time: the contract never retries a 4xx under the same one.
        idempotencyKey: createRequestId(),
      });
    },
    logger: log,
    fn: "handleCheckOut",
    dataId: "TRK-004",
    onSuccess: (closed) => {
      toast.success("Checked out", { description: closed.label });
      onDone();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "photo_required") {
        setProblem("Add a photo of the visit first: the company asks for one.");
        return;
      }
      if (isApiError(error) && error.code === "visit_closed") {
        toast.info("This visit was already closed");
        onDone();
        return;
      }
      toast.error("Not checked out", { description: toUserFacingError(error).description });
    },
  });

  return (
    <form
      noValidate
      aria-label="Check out"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        if (outcome === null) {
          setProblem("Say how the visit went.");
          return;
        }
        setProblem(null);
        void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Check out</DialogTitle>
        <DialogDescription>{visit.label}</DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {needsPhoto ? (
          <Notice tone="warning">A photo is needed before you check out. Add one first.</Notice>
        ) : null}
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium text-foreground">How did it go?</legend>
          <RadioGroup<VisitOutcome>
            aria-label="How did it go?"
            onValueChange={(next) => {
              setOutcome(next);
              setProblem(null);
            }}
            className="grid grid-cols-2 gap-2"
          >
            {VISIT_OUTCOMES.map((value) => (
              <label key={value} className="flex items-center gap-2 text-sm text-foreground">
                <RadioGroupItem value={value} />
                {VISIT_OUTCOME_LABELS[value]}
              </label>
            ))}
          </RadioGroup>
        </fieldset>
        <Field>
          <FieldLabel htmlFor="check-out-note">
            Note <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="check-out-note"
            rows={3}
            value={note}
            maxLength={2000}
            placeholder="e.g. Wants a quote for 2 acres"
            onChange={(event) => {
              setNote(event.target.value);
            }}
          />
        </Field>
        <FixPanel state={fix} onLocate={locate} action="check out" />
        {problem === null ? null : (
          <p role="alert" className="text-sm text-danger">
            {problem}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          disabled={fix.status !== "ready" || needsPhoto}
          state={save.state}
          loadingLabel="Checking out…"
          successLabel="Checked out"
          errorLabel="Not checked out"
        >
          Check out
        </Button>
      </DialogFooter>
    </form>
  );
}
