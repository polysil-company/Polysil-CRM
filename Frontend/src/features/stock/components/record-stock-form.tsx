"use client";

import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ProductSearchPicker } from "@/features/schemes/components/record-pickers";
import { useRecordStock } from "@/features/stock/api/stock.mutations";
import { warehousesQueryOptions } from "@/features/stock/api/stock.queries";
import { RECORDABLE_KINDS, type RecordableKind } from "@/features/stock/api/stock.schemas";
import { RECORDABLE_KIND_LABELS } from "@/features/stock/lib/stock-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import { WarehouseSelect } from "./warehouse-select";

const log = createLogger({
  file: "features/stock/components/record-stock-form.tsx",
  dataId: "MSTR-015",
});

/** Lines on one record; a delivery note rarely has more. */
const MAX_LINES = 30;
const QUANTITY = /^-?\d+(\.\d{1,3})?$/;

interface Line {
  readonly productId: string;
  readonly name: string;
  readonly qty: string;
}

function lineProblem(line: Line, kind: RecordableKind): string | null {
  const qty = line.qty.trim();
  if (qty === "") return "Enter how many.";
  if (!QUANTITY.test(qty)) return "A number, like 250 or 12.5.";
  if (kind === "receipt" && Number(qty) <= 0) return "Stock received is more than 0.";
  if (kind === "adjustment" && Number(qty) === 0) return "Not 0: a minus takes stock off.";
  return null;
}

/** The backend's refusals, in words. */
function refusalText(error: unknown): string {
  if (isApiError(error)) {
    if (error.code === "negative_stock")
      return "That would take a product below zero in this warehouse.";
    if (error.code === "warehouse_inactive") return "This warehouse is switched off. Pick another.";
    if (error.code === "product_inactive")
      return "A product is switched off. Remove it and try again.";
  }
  return toUserFacingError(error).title;
}

/**
 * MSTR-015 · Record stock received at a warehouse, or a correction (which may take stock off):
 * a reference such as the GRN, a note, and a quantity per product. An opening balance is a
 * receipt referenced "Opening". Dispatches move stock by themselves.
 */
export function RecordStockForm({ onClose }: { onClose: () => void }): React.JSX.Element {
  const warehouses = useQuery(warehousesQueryOptions());
  const record = useRecordStock();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [chosenWarehouse, setWarehouseId] = useState<string | null>(null);
  const warehouseId =
    chosenWarehouse ?? warehouses.data?.find((item) => item.isDefault)?.id ?? null;
  const [kind, setKind] = useState<RecordableKind>("receipt");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<readonly Line[]>([]);
  const [shown, setShown] = useState(false);
  const [serverLines, setServerLines] = useState<Readonly<Record<number, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);

  const problems = {
    warehouse: warehouseId === null ? "Choose the warehouse." : null,
    lines: lines.length === 0 ? "Add at least one product." : null,
  };
  const lineProblems = lines.map(
    (line, index) => serverLines[index] ?? (shown ? lineProblem(line, kind) : null),
  );
  const invalid =
    problems.warehouse !== null ||
    problems.lines !== null ||
    lines.some((line) => lineProblem(line, kind) !== null);

  const submit = useAsyncAction({
    action: () => {
      const body = {
        warehouse_id: warehouseId ?? "",
        kind,
        reference: reference.trim() === "" ? null : reference.trim(),
        note: note.trim() === "" ? null : note.trim(),
        lines: lines.map((line) => ({ product_id: line.productId, qty: line.qty.trim() })),
      };
      return record.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleRecordStock",
    dataId: "MSTR-015",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(kind === "receipt" ? "Stock received recorded" : "Correction recorded", {
        description: `${String(saved.length)} ${saved.length === 1 ? "product" : "products"} updated.`,
      });
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      const byLine: Record<number, string> = {};
      for (const [path, reason] of Object.entries(fields)) {
        const match = /^lines\.(\d+)\.qty$/.exec(path);
        if (match?.[1] !== undefined) byLine[Number(match[1])] = reason;
      }
      if (Object.keys(byLine).length > 0) {
        setServerLines(byLine);
        return;
      }
      setRefusal(refusalText(error));
    },
  });

  const setLine = (index: number, qty: string): void => {
    setLines(lines.map((line, position) => (position === index ? { ...line, qty } : line)));
    setServerLines({});
  };

  return (
    <form
      noValidate
      aria-label="Record stock"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (invalid) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Record stock</DialogTitle>
        <DialogDescription>
          What came in, or a correction after a count. Dispatches take stock out by themselves.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={shown && problems.warehouse !== null ? true : undefined}>
            <FieldLabel htmlFor="record-warehouse">Warehouse</FieldLabel>
            <WarehouseSelect
              id="record-warehouse"
              value={warehouseId}
              onValueChange={setWarehouseId}
              aria-invalid={shown && problems.warehouse !== null ? true : undefined}
              aria-describedby={
                shown && problems.warehouse !== null ? "record-warehouse-error" : undefined
              }
            />
            {shown && problems.warehouse !== null ? (
              <FieldError id="record-warehouse-error">{problems.warehouse}</FieldError>
            ) : null}
          </Field>
          <Field>
            <FieldLabel id="record-kind-label">What</FieldLabel>
            <ToggleGroup
              aria-labelledby="record-kind-label"
              value={[kind]}
              onValueChange={(next) => {
                const chosen = RECORDABLE_KINDS.find((value) => value === next[0]);
                if (chosen !== undefined) setKind(chosen);
              }}
              className="w-full"
            >
              {RECORDABLE_KINDS.map((value) => (
                <ToggleGroupItem key={value} value={value} className="flex-1">
                  {RECORDABLE_KIND_LABELS[value]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>
          <Field>
            <FieldLabel htmlFor="record-reference">
              Reference
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id="record-reference"
              autoComplete="off"
              maxLength={120}
              placeholder={kind === "receipt" ? "GRN 2231, or Opening" : "Count on 17 Oct"}
              value={reference}
              aria-describedby="record-reference-help"
              onChange={(event) => {
                setReference(event.target.value);
              }}
            />
            <FieldDescription id="record-reference-help">
              An opening balance is stock received referenced &ldquo;Opening&rdquo;.
            </FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="record-note">
              Note
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="record-note"
              rows={2}
              maxLength={500}
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
          </Field>
        </div>

        <section aria-labelledby="record-lines-title" className="flex flex-col gap-2">
          <h3 id="record-lines-title" className="text-sm font-medium text-foreground">
            Products
          </h3>
          {lines.length === 0 ? null : (
            <ul aria-label="Products to record" className="flex flex-col divide-y divide-border">
              {lines.map((line, index) => {
                const id = `record-qty-${String(index)}`;
                const problem = lineProblems[index] ?? null;
                return (
                  <li
                    key={line.productId}
                    className="flex flex-col gap-1 py-2 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <label htmlFor={id} className="pt-2 text-sm text-foreground">
                      {line.name}
                    </label>
                    <div className="flex items-start gap-2">
                      <div className="flex flex-col gap-1">
                        <Input
                          id={id}
                          inputMode="decimal"
                          autoComplete="off"
                          className="w-32 text-right tabular-nums"
                          placeholder={kind === "receipt" ? "250" : "−25"}
                          value={line.qty}
                          aria-invalid={problem === null ? undefined : true}
                          aria-describedby={problem === null ? undefined : `${id}-error`}
                          onChange={(event) => {
                            setLine(index, event.target.value.replace("−", "-"));
                          }}
                        />
                        {problem === null ? null : (
                          <span id={`${id}-error`} className="text-xs text-danger">
                            {problem}
                          </span>
                        )}
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${line.name}`}
                        onClick={() => {
                          setLines(lines.filter((_, position) => position !== index));
                          setServerLines({});
                        }}
                      >
                        <Icon icon={Cancel01Icon} />
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          {lines.length < MAX_LINES ? (
            <Field data-invalid={shown && problems.lines !== null ? true : undefined}>
              <FieldLabel htmlFor="record-add-product" className="sr-only">
                Add a product
              </FieldLabel>
              <ProductSearchPicker
                id="record-add-product"
                aria-describedby={
                  shown && problems.lines !== null ? "record-lines-error" : undefined
                }
                onPick={(picked) => {
                  if (lines.some((line) => line.productId === picked.id)) return;
                  setLines([...lines, { productId: picked.id, name: picked.name, qty: "" }]);
                }}
              />
              {shown && problems.lines !== null ? (
                <FieldError id="record-lines-error">{problems.lines}</FieldError>
              ) : null}
            </Field>
          ) : null}
          {kind === "adjustment" ? (
            <p className="text-xs text-muted-foreground">
              A minus takes stock off, for breakage or a recount. Stock never goes below zero.
            </p>
          ) : null}
        </section>

        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
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
          loadingLabel="Recording…"
          successLabel="Recorded"
          errorLabel="Not recorded"
        >
          Record
        </Button>
      </DialogFooter>
    </form>
  );
}
