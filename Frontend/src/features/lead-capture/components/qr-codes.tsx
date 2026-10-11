"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  Add01Icon,
  Copy01Icon,
  Download04Icon,
  Edit02Icon,
  QrCodeIcon,
  ToggleOffIcon,
  ToggleOnIcon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { QRCodeCanvas, QRCodeSVG } from "qrcode.react";
import { useRef, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { DealerPicker, type DealerChoice } from "@/features/complaints/components/dealer-picker";
import {
  useCreateQrCode,
  usePatchQrCode,
} from "@/features/lead-capture/api/lead-capture.mutations";
import { qrCodesQueryOptions } from "@/features/lead-capture/api/lead-capture.queries";
import type { QrCode } from "@/features/lead-capture/api/lead-capture.schemas";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { saveFile } from "@/lib/api/save-file";
import { formatCount } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/lead-capture/components/qr-codes.tsx",
  dataId: "LEAD-013",
});

/**
 * A printed code must scan in any light, so it is always black on white, whatever the theme.
 * These are the QR library's colour props, not interface colours.
 */
const QR_FOREGROUND = "#000000";
const QR_BACKGROUND = "#ffffff";
/** Pixels in the downloaded image: sharp on an A5 poster. */
const PRINT_SIZE = 1024;

type Editing = { readonly mode: "new" } | { readonly mode: "edit"; readonly code: QrCode };

/**
 * LEAD-013 · QR codes for printed material: a dealer's counter, a fair stall, a leaflet. Each
 * opens the enquiry page; leads from it are credited to its dealer and start in its area. Make
 * one, download it to print, copy its link, rename or re-point it, or switch it off — the code
 * and its link never change, so printed copies keep working.
 */
export function QrCodes(): React.JSX.Element {
  const query = useQuery(qrCodesQueryOptions());
  const canCreate = useCan("leads", "create");
  const canEdit = useCan("leads", "edit");
  const [editing, setEditing] = useState<Editing | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">
          A farmer who scans a code opens the enquiry form, checks their mobile on WhatsApp, and
          becomes a lead for the officer covering their area — credited to the code&apos;s dealer
          when it has one.
        </p>
        {canCreate ? (
          <Button
            onClick={() => {
              setEditing({ mode: "new" });
            }}
          >
            <Icon icon={Add01Icon} />
            New QR code
          </Button>
        ) : null}
      </div>

      <QueryView
        query={query}
        pending={<QrCodesSkeleton />}
        isEmpty={(rows) => rows.length === 0}
        empty={
          <EmptyState
            icon={QrCodeIcon}
            title="No QR codes yet"
            description="Make one for a dealer's counter, a fair stall or a leaflet, then print it."
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(rows) => (
          <ul aria-label="QR codes" className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {rows.map((code) => (
              <QrCodeCard
                key={code.id}
                code={code}
                canEdit={canEdit}
                onEdit={() => {
                  setEditing({ mode: "edit", code });
                }}
              />
            ))}
          </ul>
        )}
      </QueryView>

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent size="md">
          {editing === null ? null : (
            <QrCodeForm
              editing={editing}
              onClose={() => {
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function QrCodeCard({
  code,
  canEdit,
  onEdit,
}: {
  code: QrCode;
  canEdit: boolean;
  onEdit: () => void;
}): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const patch = usePatchQrCode();
  const idempotency = useIdempotencyKey();
  const toggle = useAsyncAction({
    action: () => {
      const body = { is_active: !code.isActive };
      return patch.mutateAsync({
        qrId: code.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: code.id, ...body }),
      });
    },
    logger: log,
    fn: "handleToggleQrCode",
    dataId: "LEAD-013",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(saved.isActive ? "Code switched on" : "Code switched off", {
        description: saved.isActive
          ? saved.label
          : "Scans now make plain website enquiries, without this code's dealer.",
      });
    },
    onError: (error) => {
      const view = toUserFacingError(error);
      toast.error(view.title, { description: view.description });
    },
  });

  const download = (): void => {
    canvasRef.current?.toBlob((blob) => {
      if (blob === null) {
        toast.error("The image couldn't be made", { description: "Try again." });
        return;
      }
      saveFile({ blob, filename: `polysil-qr-${code.code}.png` }, `polysil-qr-${code.code}.png`);
      log.info("handleDownloadQrCode", "saved the QR image", { context: { code: code.code } });
    }, "image/png");
  };

  const copy = (): void => {
    void navigator.clipboard.writeText(code.url).then(
      () => {
        toast.success("Link copied", { description: code.url });
      },
      () => {
        toast.error("The link couldn't be copied", { description: code.url });
      },
    );
  };

  return (
    <li
      aria-label={code.label}
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4"
    >
      <div className="flex items-start gap-4">
        <div className="shrink-0 rounded-md bg-scan-surface p-2" aria-hidden="true">
          <QRCodeSVG
            value={code.url}
            size={96}
            level="M"
            fgColor={QR_FOREGROUND}
            bgColor={QR_BACKGROUND}
            className={code.isActive ? undefined : "opacity-40"}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <p className="font-medium wrap-break-word text-foreground">{code.label}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={code.isActive ? "success" : "neutral"} size="sm" dot>
              {code.isActive ? "On" : "Switched off"}
            </Badge>
            <span className="font-mono text-xs text-muted-foreground">{code.code}</span>
          </div>
          <p className="text-sm text-foreground tabular-nums">
            {formatCount(code.leadCount)} {code.leadCount === 1 ? "lead" : "leads"}
          </p>
        </div>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
        <dt className="text-muted-foreground">Campaign</dt>
        <dd className="text-foreground">{code.campaign ?? "—"}</dd>
        <dt className="text-muted-foreground">Dealer</dt>
        <dd className="text-foreground">
          {code.partner?.name ?? "None: leads go to the area's officer"}
        </dd>
        <dt className="text-muted-foreground">Area</dt>
        <dd className="text-foreground">{code.territory?.name ?? "The farmer chooses"}</dd>
        <dt className="text-muted-foreground">Made</dt>
        <dd className="text-foreground">
          <RelativeDate value={code.createdAt} />
        </dd>
      </dl>
      {/* The full-size image the download saves; never shown. */}
      <QRCodeCanvas
        ref={canvasRef}
        value={code.url}
        size={PRINT_SIZE}
        level="M"
        marginSize={4}
        fgColor={QR_FOREGROUND}
        bgColor={QR_BACKGROUND}
        className="hidden"
        aria-hidden="true"
      />
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={download}
          aria-label={`Download ${code.label} to print`}
        >
          <Icon icon={Download04Icon} />
          Download to print
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={copy}
          aria-label={`Copy the link for ${code.label}`}
        >
          <Icon icon={Copy01Icon} />
          Copy link
        </Button>
        {canEdit ? (
          <>
            <Button size="sm" variant="ghost" onClick={onEdit} aria-label={`Edit ${code.label}`}>
              <Icon icon={Edit02Icon} />
              Edit
            </Button>
            <Button
              size="sm"
              variant="ghost"
              state={toggle.state}
              loadingLabel="Saving…"
              successLabel="Saved"
              errorLabel="Not saved"
              aria-label={`${code.isActive ? "Switch off" : "Switch on"} ${code.label}`}
              onClick={() => {
                void toggle.run();
              }}
            >
              <Icon icon={code.isActive ? ToggleOffIcon : ToggleOnIcon} />
              {code.isActive ? "Switch off" : "Switch on"}
            </Button>
          </>
        ) : null}
      </div>
    </li>
  );
}

// ── new and edit (LEAD-013) ────────────────────────────────────────────────────────

interface QrForm {
  label: string;
  campaign: string;
  dealer: DealerChoice | null;
  territory: TerritoryChoice | null;
}

const qrFormSchema: z.ZodType<QrForm, QrForm> = z.object({
  label: z
    .string()
    .trim()
    .min(1, "Name it so staff recognise it: the dealer, the stall, the leaflet.")
    .max(120, "Keep it under 120 characters."),
  campaign: z.string().trim().max(120, "Keep it under 120 characters."),
  dealer: z.custom<DealerChoice | null>(() => true),
  territory: z.custom<TerritoryChoice | null>(() => true),
});

const SERVER_FIELDS = {
  label: "label",
  campaign: "campaign",
  partner_id: "dealer",
  territory_id: "territory",
} as const satisfies Readonly<Record<string, keyof QrForm>>;

function QrCodeForm({
  editing,
  onClose,
}: {
  editing: Editing;
  onClose: () => void;
}): React.JSX.Element {
  const create = useCreateQrCode();
  const patch = usePatchQrCode();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<string | null>(null);
  const existing = editing.mode === "edit" ? editing.code : null;
  const form = useForm<QrForm>({
    resolver: zodResolver(qrFormSchema),
    defaultValues: {
      label: existing?.label ?? "",
      campaign: existing?.campaign ?? "",
      dealer:
        existing?.partner == null ? null : { id: existing.partner.id, name: existing.partner.name },
      territory: existing?.territory ?? null,
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const save = useAsyncAction({
    action: (values: QrForm) => {
      const body = {
        label: values.label.trim(),
        campaign: values.campaign.trim() === "" ? null : values.campaign.trim(),
        partner_id: values.dealer?.id ?? null,
        territory_id: values.territory?.id ?? null,
      };
      return existing === null
        ? create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) })
        : patch.mutateAsync({
            qrId: existing.id,
            body,
            idempotencyKey: idempotency.keyFor({ id: existing.id, ...body }),
          });
    },
    logger: log,
    fn: existing === null ? "handleCreateQrCode" : "handleEditQrCode",
    dataId: "LEAD-013",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(existing === null ? "QR code made" : "QR code saved", {
        description: existing === null ? "Download it to print." : saved.label,
      });
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      let placed = false;
      for (const [api, name] of Object.entries(SERVER_FIELDS)) {
        const reason = fields[api];
        if (reason === undefined) continue;
        placed = true;
        form.setError(name, {
          type: "server",
          message:
            api === "partner_id"
              ? "This dealer is closed or outside your area. Choose another."
              : reason,
        });
      }
      if (!placed) setRefusal(toUserFacingError(error).description);
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => save.run(values))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>{existing === null ? "New QR code" : `Edit ${existing.label}`}</DialogTitle>
        <DialogDescription>
          {existing === null
            ? "It opens the enquiry form. Print it once it's made."
            : "The code and its link stay the same, so printed copies keep working. A new dealer gets new leads only."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="flex flex-col gap-4">
          <Field data-invalid={errors.label ? true : undefined}>
            <FieldLabel htmlFor="qr-label">Name</FieldLabel>
            <Input
              id="qr-label"
              autoComplete="off"
              placeholder="Counter at Khodiyar Irrigation"
              aria-invalid={errors.label ? true : undefined}
              aria-describedby={errors.label ? "qr-label-error" : undefined}
              {...form.register("label")}
            />
            <FieldError id="qr-label-error">{errors.label?.message}</FieldError>
          </Field>
          <Field data-invalid={errors.campaign ? true : undefined}>
            <FieldLabel htmlFor="qr-campaign">
              Campaign
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id="qr-campaign"
              autoComplete="off"
              placeholder="Kharif 2026"
              aria-invalid={errors.campaign ? true : undefined}
              aria-describedby={errors.campaign ? "qr-campaign-error" : undefined}
              {...form.register("campaign")}
            />
            <FieldError id="qr-campaign-error">{errors.campaign?.message}</FieldError>
          </Field>
          <Controller
            control={form.control}
            name="dealer"
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.error ? true : undefined}>
                <FieldLabel htmlFor="qr-dealer">
                  Dealer
                  <span className="font-normal text-subtle-foreground">(optional)</span>
                </FieldLabel>
                <DealerPicker id="qr-dealer" value={field.value} onValueChange={field.onChange} />
                {fieldState.error ? null : (
                  <FieldDescription>Leads from this code are credited to them.</FieldDescription>
                )}
                <FieldError>{fieldState.error?.message}</FieldError>
              </Field>
            )}
          />
          <Controller
            control={form.control}
            name="territory"
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.error ? true : undefined}>
                <FieldLabel htmlFor="qr-territory">
                  Area
                  <span className="font-normal text-subtle-foreground">(optional)</span>
                </FieldLabel>
                <TerritoryPicker
                  id="qr-territory"
                  value={field.value}
                  levels={["district", "taluka"]}
                  onValueChange={field.onChange}
                  onBlur={field.onBlur}
                />
                {fieldState.error ? null : (
                  <FieldDescription>
                    Already chosen on the form, so the farmer skips it.
                  </FieldDescription>
                )}
                <FieldError>{fieldState.error?.message}</FieldError>
              </Field>
            )}
          />
        </FieldGroup>
        {refusal === null ? null : (
          <p role="alert" className="mt-4 rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {existing === null ? "Make the code" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function QrCodesSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading QR codes"
      className="grid gap-3 md:grid-cols-2 xl:grid-cols-3"
    >
      {[0, 1, 2].map((key) => (
        <div key={key} className="flex gap-4 rounded-xl border border-border p-4">
          <Skeleton className="size-28 shrink-0" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
