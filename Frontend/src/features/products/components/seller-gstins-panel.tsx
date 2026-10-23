"use client";

import { Add01Icon, Certificate01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAddLut, useDeleteLut } from "@/features/products/api/seller-gstins.mutations";
import { sellerGstinsQueryOptions } from "@/features/products/api/seller-gstins.queries";
import {
  ARN_PATTERN,
  type AddLutRequest,
  type Lut,
  type SellerGstin,
} from "@/features/products/api/seller-gstins.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/products/components/seller-gstins-panel.tsx",
  dataId: "MSTR-018",
});

/** The financial year a day falls in, by its starting year: 2026-05-01 → 2026. */
export function financialYearOf(day: string): number {
  const year = Number(day.slice(0, 4));
  return Number(day.slice(5, 7)) >= 4 ? year : year - 1;
}

/** "2026-27". */
export function financialYearLabel(startYear: number): string {
  return `${String(startYear)}-${String(startYear + 1).slice(2)}`;
}

/** Whether a LUT covers a day. */
export function lutCovers(lut: Lut, day: string): boolean {
  return lut.validFrom <= day && day <= lut.validTo;
}

/**
 * MSTR-018 · Our GST registrations and their LUTs by financial year. An export under the LUT
 * setting needs a LUT of the selling registration covering the document's date. Those who edit
 * products add a LUT and remove one no document carries.
 */
export function SellerGstinsPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const query = useQuery(sellerGstinsQueryOptions());
  const [adding, setAdding] = useState<SellerGstin | null>(null);
  const [removing, setRemoving] = useState<{ gstin: SellerGstin; lut: Lut } | null>(null);

  return (
    <Card>
      <CardHeader className="flex-col gap-0.5">
        <CardTitle>Seller GSTINs</CardTitle>
        <CardDescription>
          Our GST registrations. An export under a LUT needs one covering its date on the
          registration that sells.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.status === "pending" ? (
          <div
            aria-busy="true"
            aria-label="Loading the registrations"
            className="flex flex-col gap-3"
          >
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        ) : query.data.length === 0 ? (
          <EmptyState
            icon={Certificate01Icon}
            title="No registrations yet"
            description="The backend lists our GST registrations here once they are set up."
            className="py-8"
          />
        ) : (
          <ul aria-label="Seller GSTINs" className="flex flex-col gap-3">
            {query.data.map((gstin) => (
              <GstinCard
                key={gstin.id}
                gstin={gstin}
                canEdit={canEdit}
                onAdd={() => {
                  setAdding(gstin);
                }}
                onRemove={(lut) => {
                  setRemoving({ gstin, lut });
                }}
              />
            ))}
          </ul>
        )}
      </CardContent>
      <Dialog
        open={adding !== null}
        onOpenChange={(open) => {
          if (!open) setAdding(null);
        }}
      >
        <DialogContent size="sm">
          {adding === null ? null : (
            <AddLutForm
              gstin={adding}
              onDone={() => {
                setAdding(null);
              }}
            />
          )}
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
            <RemoveLutForm
              gstin={removing.gstin}
              lut={removing.lut}
              onDone={() => {
                setRemoving(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function GstinCard({
  gstin,
  canEdit,
  onAdd,
  onRemove,
}: {
  gstin: SellerGstin;
  canEdit: boolean;
  onAdd: () => void;
  onRemove: (lut: Lut) => void;
}): React.JSX.Element {
  const today = todayInIndia();
  const covered = gstin.luts.some((lut) => lut.validTo >= today && lut.validFrom <= today);
  const titleId = `gstin-${gstin.id}`;
  return (
    <li
      aria-labelledby={titleId}
      className="flex flex-col gap-3 rounded-lg border border-border p-3 sm:p-4"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span id={titleId} className="font-mono text-sm font-semibold text-foreground">
              {gstin.gstin}
            </span>
            {gstin.isDefault ? (
              <Badge variant="info" size="sm">
                Default
              </Badge>
            ) : null}
            {gstin.isActive ? null : (
              <Badge variant="neutral" size="sm">
                Inactive
              </Badge>
            )}
          </div>
          <span className="text-xs text-muted-foreground">
            {gstin.legalName} · {gstin.stateCode}
          </span>
        </div>
        {canEdit ? (
          <Button variant="outline" size="sm" className="self-start" onClick={onAdd}>
            <Icon icon={Add01Icon} />
            Add LUT
          </Button>
        ) : null}
      </div>
      {gstin.isActive && !covered ? (
        <Notice tone="warning">
          No LUT covers today. An export under the LUT setting from this registration can&apos;t be
          submitted until this year&apos;s is recorded.
        </Notice>
      ) : null}
      {gstin.luts.length === 0 ? null : (
        <ul aria-label={`LUTs of ${gstin.gstin}`} className="flex flex-col divide-y divide-border">
          {gstin.luts.map((lut) => (
            <li
              key={lut.id}
              className="flex flex-col gap-1 py-2 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-3"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium text-foreground tabular-nums">
                    {financialYearLabel(financialYearOf(lut.validFrom))}
                  </span>
                  <span className="font-mono text-muted-foreground">{lut.arn}</span>
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatBusinessDay(lut.validFrom)} to {formatBusinessDay(lut.validTo)}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {lutCovers(lut, today) ? (
                  <Badge variant="success" size="sm">
                    Current
                  </Badge>
                ) : null}
                {lut.inUse ? (
                  <Badge variant="outline" size="sm">
                    On a document
                  </Badge>
                ) : canEdit ? (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove LUT ${lut.arn}`}
                    onClick={() => {
                      onRemove(lut);
                    }}
                  >
                    <Icon icon={Delete02Icon} />
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

type LutField = "arn" | "from" | "to";

/** What the form holds, as typed. */
export interface LutDraft {
  readonly arn: string;
  readonly from: string;
  readonly to: string;
}

/** This financial year's dates, the form's starting point. */
export function currentYearDraft(today: string): LutDraft {
  const start = financialYearOf(today);
  return { arn: "", from: `${String(start)}-04-01`, to: `${String(start + 1)}-03-31` };
}

/** What is wrong before the LUT can be sent. */
export function lutProblems(draft: LutDraft): Partial<Record<LutField, string>> {
  return {
    ...(ARN_PATTERN.test(draft.arn.trim()) ? {} : { arn: "10 to 20 letters and digits." }),
    ...(draft.from === "" ? { from: "Choose the first day." } : {}),
    ...(draft.to === ""
      ? { to: "Choose the last day." }
      : draft.from !== "" && draft.to < draft.from
        ? { to: "The last day comes after the first." }
        : draft.from !== "" && financialYearOf(draft.from) !== financialYearOf(draft.to)
          ? { to: "A LUT covers one financial year: it ends by 31 March." }
          : {}),
  };
}

export function requestOfLut(draft: LutDraft): AddLutRequest {
  return { arn: draft.arn.trim().toUpperCase(), valid_from: draft.from, valid_to: draft.to };
}

/** The backend's refusals, on the field they concern. */
export function lutRefusal(error: unknown): Partial<Record<LutField, string>> | null {
  if (!isApiError(error)) return null;
  switch (error.code) {
    case "lut_duplicate":
      return { arn: "This ARN is already recorded." };
    case "lut_overlap":
      return { from: "Another LUT of this registration covers some of these dates." };
    case "lut_dates":
      return { to: "A LUT covers one financial year, 1 April to 31 March." };
    default: {
      const fields = readFieldErrors(error) ?? {};
      const mapped: Partial<Record<LutField, string>> = {
        ...(fields.arn === undefined ? {} : { arn: fields.arn }),
        ...(fields.valid_from === undefined ? {} : { from: fields.valid_from }),
        ...(fields.valid_to === undefined ? {} : { to: fields.valid_to }),
      };
      return Object.keys(mapped).length > 0 ? mapped : null;
    }
  }
}

/** MSTR-018 · Record a LUT for one financial year. A LUT is never edited, only removed and added. */
function AddLutForm({
  gstin,
  onDone,
}: {
  gstin: SellerGstin;
  onDone: () => void;
}): React.JSX.Element {
  const [draft, setDraft] = useState<LutDraft>(() => currentYearDraft(todayInIndia()));
  const [problems, setProblems] = useState<Partial<Record<LutField, string>>>({});
  const mutation = useAddLut();
  const idempotency = useIdempotencyKey();

  const save = useAsyncAction({
    action: () => {
      const body = requestOfLut(draft);
      return mutation.mutateAsync({
        gstinId: gstin.id,
        body,
        idempotencyKey: idempotency.keyFor({ gstin: gstin.id, ...body }),
      });
    },
    logger: log,
    fn: "handleAddLut",
    dataId: "MSTR-018",
    onSuccess: (lut) => {
      idempotency.reset();
      toast.success("LUT recorded", {
        description: `${lut.arn} for ${financialYearLabel(financialYearOf(lut.validFrom))}.`,
      });
      onDone();
    },
    onError: (error) => {
      const refusal = lutRefusal(error);
      if (refusal !== null) {
        setProblems(refusal);
        return;
      }
      toast.error("LUT not recorded", { description: toUserFacingError(error).description });
    },
  });

  const set = (next: Partial<LutDraft>): void => {
    setDraft((before) => ({ ...before, ...next }));
  };
  const invalid = (field: LutField): true | undefined =>
    problems[field] === undefined ? undefined : true;

  return (
    <form
      noValidate
      aria-label={`Add a LUT to ${gstin.gstin}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        const found = lutProblems(draft);
        setProblems(found);
        if (Object.keys(found).length === 0) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Add a LUT</DialogTitle>
        <DialogDescription>
          For <span className="font-mono">{gstin.gstin}</span>, one financial year. Next year&apos;s
          may be added before this one ends.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={invalid("arn")}>
          <FieldLabel htmlFor="lut-arn">ARN</FieldLabel>
          <Input
            id="lut-arn"
            value={draft.arn}
            maxLength={20}
            autoComplete="off"
            spellCheck={false}
            className="font-mono uppercase"
            aria-invalid={invalid("arn")}
            aria-describedby={invalid("arn") ? "lut-arn-error" : "lut-arn-hint"}
            onChange={(event) => {
              set({ arn: event.target.value });
            }}
          />
          {problems.arn === undefined ? (
            <FieldDescription id="lut-arn-hint">
              The acknowledgement reference number from the GST portal.
            </FieldDescription>
          ) : null}
          <FieldError id="lut-arn-error">{problems.arn}</FieldError>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={invalid("from")}>
            <FieldLabel htmlFor="lut-from">Valid from</FieldLabel>
            <Input
              id="lut-from"
              type="date"
              value={draft.from}
              aria-invalid={invalid("from")}
              aria-describedby={invalid("from") ? "lut-from-error" : undefined}
              onChange={(event) => {
                set({ from: event.target.value });
              }}
            />
            <FieldError id="lut-from-error">{problems.from}</FieldError>
          </Field>
          <Field data-invalid={invalid("to")}>
            <FieldLabel htmlFor="lut-to">Valid to</FieldLabel>
            <Input
              id="lut-to"
              type="date"
              value={draft.to}
              aria-invalid={invalid("to")}
              aria-describedby={invalid("to") ? "lut-to-error" : "lut-to-hint"}
              onChange={(event) => {
                set({ to: event.target.value });
              }}
            />
            {problems.to === undefined ? (
              <FieldDescription id="lut-to-hint">By 31 March.</FieldDescription>
            ) : null}
            <FieldError id="lut-to-error">{problems.to}</FieldError>
          </Field>
        </div>
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Recorded"
          errorLabel="Not recorded"
        >
          Add the LUT
        </Button>
      </DialogFooter>
    </form>
  );
}

/** MSTR-018 · Remove a LUT no document carries, to add it again correctly. */
function RemoveLutForm({
  gstin,
  lut,
  onDone,
}: {
  gstin: SellerGstin;
  lut: Lut;
  onDone: () => void;
}): React.JSX.Element {
  const mutation = useDeleteLut();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<string | null>(null);
  const submit = useAsyncAction({
    action: () =>
      mutation.mutateAsync({
        gstinId: gstin.id,
        lutId: lut.id,
        idempotencyKey: idempotency.keyFor({ remove: lut.id }),
      }),
    logger: log,
    fn: "handleDeleteLut",
    dataId: "MSTR-018",
    onSuccess: () => {
      toast.success("LUT removed", { description: lut.arn });
      onDone();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "lut_in_use") {
        setRefusal("A quotation or order now carries this LUT, so it stays.");
        return;
      }
      setRefusal(toUserFacingError(error).description);
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>Remove this LUT?</DialogTitle>
        <DialogDescription>
          <span className="font-mono">{lut.arn}</span>,{" "}
          {financialYearLabel(financialYearOf(lut.validFrom))}. No document carries it yet. Add it
          again if it was mistyped.
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
