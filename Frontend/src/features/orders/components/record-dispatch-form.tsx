"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type * as React from "react";
import { useForm, useFormState, type UseFormReturn } from "react-hook-form";
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
import { Input } from "@/components/ui/input";
import { useCreateDispatch } from "@/features/orders/api/orders.mutations";
import {
  dispatchFormSchemaFor,
  type CreateDispatchRequest,
  type DispatchForm,
  type Order,
} from "@/features/orders/api/orders.schemas";
import {
  DISPATCH_WARNING_LABELS,
  formatOrderQty,
  orderNumber,
} from "@/features/orders/lib/order-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import { RefusalAlert, useCloseAfterSuccess, useOrderRefusal } from "./order-dialog-shared";

const log = createLogger({
  file: "features/orders/components/record-dispatch-form.tsx",
  dataId: "DISP-002",
});

/** "2026-09-29T14:05" for a date-time field, in the device's own time (India for this team). */
function localDateTime(date: Date): string {
  const pad = (value: number): string => String(value).padStart(2, "0");
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/**
 * DISP-002 · Records what left against the order: how much of each open line, when, and the
 * challan, invoice and vehicle. Each quantity is at most what is open, in the line's unit.
 * Recorded anyway, with a warning: an invoice dated before its challan, and an invoice
 * number already used — this system does not issue invoices, so it only points them out.
 */
export function RecordDispatchForm({
  order,
  onClose,
}: {
  order: Order;
  onClose: () => void;
}): React.JSX.Element {
  const record = useCreateDispatch();
  const idempotency = useIdempotencyKey();
  const { refusal, handle, clear } = useOrderRefusal(order.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const openLines = order.lines.filter((line) => Number(line.qtyOpen) > 0);
  const form = useForm<DispatchForm>({
    resolver: zodResolver(dispatchFormSchemaFor(openLines)),
    defaultValues: {
      dispatchedAt: localDateTime(new Date()),
      dcNo: "",
      dcDate: "",
      invoiceNo: "",
      invoiceDate: "",
      transporter: "",
      vehicleNo: "",
      lines: openLines.map((line) => ({ orderLineId: line.id, qty: "" })),
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const submit = useAsyncAction({
    action: (values: DispatchForm) => {
      const sent = values.lines.filter((line) => line.qty !== "" && Number(line.qty) > 0);
      const body: CreateDispatchRequest = {
        dc_no: orNull(values.dcNo),
        dc_date: orNull(values.dcDate),
        invoice_no: orNull(values.invoiceNo),
        invoice_date: orNull(values.invoiceDate),
        dispatched_at: new Date(values.dispatchedAt).toISOString(),
        transporter: orNull(values.transporter),
        vehicle_no: orNull(values.vehicleNo)?.toUpperCase() ?? null,
        lines: sent.map((line) => ({ order_line_id: line.orderLineId, qty: line.qty })),
      };
      return record.mutateAsync({
        id: order.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: order.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleRecordDispatch",
    dataId: "DISP-002",
    onSuccess: (dispatch) => {
      idempotency.reset();
      const warnings = dispatch.warnings.map((code) => DISPATCH_WARNING_LABELS[code] ?? code);
      if (warnings.length > 0) {
        toast.warning(`${dispatch.dispatchNo} recorded, with a warning`, {
          description: warnings.join(" "),
        });
      } else {
        toast.success(`${dispatch.dispatchNo} recorded`, { description: orderNumber(order) });
      }
      closeSoon();
    },
    onError: (error) => {
      mapServerErrors(error);
      handle(error);
    },
  });

  /** The backend names lines by their place in the request; the form shows every open line. */
  function mapServerErrors(error: unknown): void {
    const fields = readFieldErrors(error);
    if (fields === null) {
      return;
    }
    const values = form.getValues();
    const sentIndexes = values.lines
      .map((line, index) => ({ line, index }))
      .filter(({ line }) => line.qty !== "" && Number(line.qty) > 0)
      .map(({ index }) => index);
    for (const [key, message] of Object.entries(fields)) {
      const match = /^lines\[(\d+)\]\.qty$/.exec(key);
      const formIndex = match?.[1] === undefined ? undefined : sentIndexes[Number(match[1])];
      if (formIndex !== undefined) {
        form.setError(`lines.${formIndex}.qty`, { type: "server", message });
      } else if (key === "dispatched_at") {
        form.setError("dispatchedAt", { type: "server", message });
      }
    }
  }

  const fillOpen = (): void => {
    openLines.forEach((line, index) => {
      form.setValue(`lines.${index}.qty`, formatOrderQty(line.qtyOpen, line.uomDecimals), {
        shouldValidate: true,
        shouldDirty: true,
      });
    });
  };

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        clear();
        void form.handleSubmit((values) => submit.run(values))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Record a dispatch</DialogTitle>
        <DialogDescription>
          {orderNumber(order)} · {order.party.name}. Enter what left in this consignment; leave an
          item empty if none of it went.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <div className="flex flex-col gap-5">
          <fieldset className="flex flex-col gap-3">
            <legend className="sr-only">What left, item by item</legend>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p aria-hidden="true" className="text-sm font-medium text-foreground">
                Items
              </p>
              <Button type="button" variant="ghost" size="sm" onClick={fillOpen}>
                Everything open
              </Button>
            </div>
            <ul className="flex flex-col gap-3">
              {openLines.map((line, index) => {
                const error = errors.lines?.[index]?.qty?.message;
                const id = `dispatch-line-${line.id}`;
                return (
                  <li
                    key={line.id}
                    className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-start sm:gap-4"
                  >
                    <label htmlFor={id} className="flex min-w-0 flex-col gap-0.5">
                      <span className="text-sm text-foreground">
                        {line.lineNo}. {line.description}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatOrderQty(line.qtyOpen, line.uomDecimals)} {line.uom} open of{" "}
                        {formatOrderQty(line.qty, line.uomDecimals)}
                      </span>
                    </label>
                    <div className="flex flex-col gap-1 sm:w-36">
                      <Input
                        id={id}
                        inputMode={line.uomDecimals === 0 ? "numeric" : "decimal"}
                        placeholder="0"
                        aria-invalid={error === undefined ? undefined : true}
                        aria-describedby={error === undefined ? undefined : `${id}-error`}
                        className="text-right tabular-nums"
                        {...form.register(`lines.${index}.qty`)}
                      />
                      <FieldError id={`${id}-error`}>{error}</FieldError>
                    </div>
                  </li>
                );
              })}
            </ul>
            {errors.lines?.root?.message !== undefined || errors.lines?.message !== undefined ? (
              <p role="alert" className="text-sm text-danger">
                {errors.lines.root?.message ?? errors.lines.message}
              </p>
            ) : null}
          </fieldset>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field data-invalid={errors.dispatchedAt ? true : undefined} className="sm:col-span-2">
              <FieldLabel htmlFor="dispatch-at">Left on</FieldLabel>
              <Input
                id="dispatch-at"
                type="datetime-local"
                max={localDateTime(new Date())}
                aria-invalid={errors.dispatchedAt ? true : undefined}
                aria-describedby={
                  errors.dispatchedAt ? "dispatch-at-error" : "dispatch-at-description"
                }
                {...form.register("dispatchedAt")}
              />
              {errors.dispatchedAt ? null : (
                <FieldDescription id="dispatch-at-description">
                  When the goods left the warehouse; not in the future.
                </FieldDescription>
              )}
              <FieldError id="dispatch-at-error">{errors.dispatchedAt?.message}</FieldError>
            </Field>
            <TextField
              form={form}
              name="dcNo"
              id="dispatch-dc-no"
              label="Challan number"
              error={errors.dcNo?.message}
            />
            <Field>
              <FieldLabel htmlFor="dispatch-dc-date">
                Challan date <span className="font-normal text-muted-foreground">(optional)</span>
              </FieldLabel>
              <Input id="dispatch-dc-date" type="date" {...form.register("dcDate")} />
            </Field>
            <TextField
              form={form}
              name="invoiceNo"
              id="dispatch-invoice-no"
              label="Invoice number"
              description="From your accounts system; this one doesn't issue invoices."
              error={errors.invoiceNo?.message}
            />
            <Field>
              <FieldLabel htmlFor="dispatch-invoice-date">
                Invoice date <span className="font-normal text-muted-foreground">(optional)</span>
              </FieldLabel>
              <Input id="dispatch-invoice-date" type="date" {...form.register("invoiceDate")} />
            </Field>
            <TextField
              form={form}
              name="transporter"
              id="dispatch-transporter"
              label="Transporter"
              error={errors.transporter?.message}
            />
            <TextField
              form={form}
              name="vehicleNo"
              id="dispatch-vehicle"
              label="Vehicle number"
              error={errors.vehicleNo?.message}
            />
          </div>
        </div>
        <RefusalAlert refusal={refusal} />
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
          Record dispatch
        </Button>
      </DialogFooter>
    </form>
  );
}

type TextFieldName = "dcNo" | "invoiceNo" | "transporter" | "vehicleNo";

function TextField({
  form,
  name,
  id,
  label,
  description,
  error,
}: {
  form: UseFormReturn<DispatchForm>;
  name: TextFieldName;
  id: string;
  label: string;
  description?: string;
  error: string | undefined;
}): React.JSX.Element {
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label} <span className="font-normal text-muted-foreground">(optional)</span>
      </FieldLabel>
      <Input
        id={id}
        autoComplete="off"
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={
          error === undefined
            ? description === undefined
              ? undefined
              : `${id}-description`
            : `${id}-error`
        }
        {...form.register(name)}
      />
      {error === undefined && description !== undefined ? (
        <FieldDescription id={`${id}-description`}>{description}</FieldDescription>
      ) : null}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}
