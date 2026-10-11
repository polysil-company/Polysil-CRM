"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import type * as React from "react";
import { useForm, useFormState, useWatch } from "react-hook-form";
import { toast } from "sonner";

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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import {
  useCancelOrder,
  useCloseOrderShort,
  useDeleteOrder,
  usePatchOrder,
  useSubmitOrder,
  useVoidDispatch,
} from "@/features/orders/api/orders.mutations";
import {
  PAYMENT_TERMS,
  orderHeaderFormSchema,
  requiredRemarkFormSchema,
  type Dispatch,
  type Order,
  type OrderHeaderForm,
  type RequiredRemarkForm,
} from "@/features/orders/api/orders.schemas";
import {
  PAYMENT_TERMS_LABELS,
  orderNumber,
  stepRoleLabel,
} from "@/features/orders/lib/order-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { RefusalAlert, useCloseAfterSuccess, useOrderRefusal } from "./order-dialog-shared";
import { RecordDispatchForm } from "./record-dispatch-form";

const log = createLogger({
  file: "features/orders/components/order-action-dialog.tsx",
  dataId: "SO-004",
});

/** Which action's dialog is open. */
export type OrderDialog =
  | { readonly kind: "submit" }
  | { readonly kind: "edit" }
  | { readonly kind: "delete" }
  | { readonly kind: "cancel" }
  | { readonly kind: "dispatch" }
  | { readonly kind: "close-short" }
  | { readonly kind: "void"; readonly dispatch: Dispatch };

export interface OrderActionDialogProps {
  order: Order;
  /** The open dialog; null when none. */
  dialog: OrderDialog | null;
  onClose: () => void;
}

/**
 * SO-003, SO-004, DISP-002 · Confirms an action on an order: submit, edit the header, delete a
 * never-submitted draft, cancel, record a dispatch, close short, void a dispatch. A refusal
 * because someone else moved the order closes the dialog, says so, and shows the latest; any
 * other refusal stays in the dialog with what to do next.
 */
export function OrderActionDialog({
  order,
  dialog,
  onClose,
}: OrderActionDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={dialog !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent size={dialog?.kind === "dispatch" ? "lg" : "sm"}>
        {dialog?.kind === "submit" ? <SubmitForm order={order} onClose={onClose} /> : null}
        {dialog?.kind === "edit" ? <HeaderForm order={order} onClose={onClose} /> : null}
        {dialog?.kind === "delete" ? <DeleteForm order={order} onClose={onClose} /> : null}
        {dialog?.kind === "cancel" ? (
          <RemarkForm order={order} action="cancel" onClose={onClose} />
        ) : null}
        {dialog?.kind === "close-short" ? (
          <RemarkForm order={order} action="close-short" onClose={onClose} />
        ) : null}
        {dialog?.kind === "void" ? (
          <RemarkForm order={order} action="void" dispatch={dialog.dispatch} onClose={onClose} />
        ) : null}
        {dialog?.kind === "dispatch" ? (
          <RecordDispatchForm order={order} onClose={onClose} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

interface FormProps {
  order: Order;
  onClose: () => void;
}

// ── submit (SO-004) ─────────────────────────────────────────────────────────────

function SubmitForm({ order, onClose }: FormProps): React.JSX.Element {
  const submitOrder = useSubmitOrder();
  const idempotency = useIdempotencyKey();
  const { refusal, handle, clear } = useOrderRefusal(order.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const resubmit = order.lastRejection !== null;

  const submit = useAsyncAction({
    action: () => {
      const body = { expected_status: "draft" as const };
      return submitOrder.mutateAsync({
        id: order.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: order.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleSubmitOrder",
    dataId: "SO-004",
    onSuccess: (submitted) => {
      idempotency.reset();
      const first = submitted.approval?.steps.find((step) => step.decision === null);
      toast.success(`${orderNumber(submitted)} submitted`, {
        description:
          first === undefined
            ? "It waits for approval."
            : `It waits on ${stepRoleLabel(first.role)} first.`,
      });
      closeSoon();
    },
    onError: (error) => {
      // A price change re-prices the draft, so the next submit is a new request.
      idempotency.reset();
      handle(error);
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        clear();
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {resubmit ? "Submit again for approval?" : "Submit for approval?"}
        </DialogTitle>
        <DialogDescription>
          {order.party.name} · {formatInr(order.totals.total, { paise: true })}.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-muted-foreground">
          {order.orderNo === null ? <li>The order gets its number now.</li> : null}
          <li>Prices are checked again at the order&apos;s price date, and GST at today&apos;s.</li>
          <li>Managers approve it by value, then Accounts, then Dispatch.</li>
          <li>It can&apos;t be edited while it waits; a return brings it back to draft.</li>
        </ul>
        <RefusalAlert refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Not yet
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Submitting…"
          successLabel="Submitted"
          errorLabel="Not submitted"
        >
          Submit
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── the draft's header (SO-003) ─────────────────────────────────────────────────

function HeaderForm({ order, onClose }: FormProps): React.JSX.Element {
  const patch = usePatchOrder();
  const idempotency = useIdempotencyKey();
  const { refusal, handle, clear } = useOrderRefusal(order.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const form = useForm<OrderHeaderForm>({
    resolver: zodResolver(orderHeaderFormSchema),
    defaultValues: {
      deliveryAddress: order.deliveryAddress ?? "",
      paymentTerms: order.paymentTerms,
      remarks: order.remarks ?? "",
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const paymentTerms = useWatch({ control: form.control, name: "paymentTerms" });

  const submit = useAsyncAction({
    action: (values: OrderHeaderForm) => {
      const body = {
        delivery_address: values.deliveryAddress === "" ? null : values.deliveryAddress,
        payment_terms: values.paymentTerms,
        remarks: values.remarks === "" ? null : values.remarks,
        expected_status: "draft" as const,
      };
      return patch.mutateAsync({
        id: order.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: order.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleSaveOrderHeader",
    dataId: "SO-003",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Order saved");
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields?.delivery_address !== undefined) {
        form.setError("deliveryAddress", { type: "server", message: fields.delivery_address });
      }
      if (fields?.remarks !== undefined) {
        form.setError("remarks", { type: "server", message: fields.remarks });
      }
      handle(error);
    },
  });

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
        <DialogTitle>Delivery and terms</DialogTitle>
        <DialogDescription>
          The items and prices come from the quotations, so they stay as they are.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <div className="flex flex-col gap-4">
          <Field data-invalid={errors.deliveryAddress ? true : undefined}>
            <FieldLabel htmlFor="order-delivery-address">Deliver to</FieldLabel>
            <Textarea
              id="order-delivery-address"
              rows={3}
              aria-invalid={errors.deliveryAddress ? true : undefined}
              aria-describedby={errors.deliveryAddress ? "order-delivery-address-error" : undefined}
              {...form.register("deliveryAddress")}
            />
            <FieldError id="order-delivery-address-error">
              {errors.deliveryAddress?.message}
            </FieldError>
          </Field>
          <Field>
            <FieldLabel id="order-payment-terms-label">Payment terms</FieldLabel>
            <RadioGroup
              aria-labelledby="order-payment-terms-label"
              value={paymentTerms}
              onValueChange={(value) => {
                const terms = PAYMENT_TERMS.find((item) => item === value);
                if (terms !== undefined) {
                  form.setValue("paymentTerms", terms, { shouldDirty: true });
                }
              }}
              className="flex flex-wrap gap-4"
            >
              {PAYMENT_TERMS.map((terms) => (
                <div key={terms} className="flex items-center gap-2">
                  <RadioGroupItem id={`order-terms-${terms}`} value={terms} />
                  <Label htmlFor={`order-terms-${terms}`} className="font-normal">
                    {PAYMENT_TERMS_LABELS[terms]}
                  </Label>
                </div>
              ))}
            </RadioGroup>
            <FieldDescription>Recorded for Accounts; there is no credit check.</FieldDescription>
          </Field>
          <Field data-invalid={errors.remarks ? true : undefined}>
            <FieldLabel htmlFor="order-remarks">
              Remarks <span className="font-normal text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="order-remarks"
              rows={3}
              aria-invalid={errors.remarks ? true : undefined}
              aria-describedby={errors.remarks ? "order-remarks-error" : undefined}
              {...form.register("remarks")}
            />
            <FieldError id="order-remarks-error">{errors.remarks?.message}</FieldError>
          </Field>
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
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── delete a never-submitted draft (SO-003) ─────────────────────────────────────

function DeleteForm({ order, onClose }: FormProps): React.JSX.Element {
  const remove = useDeleteOrder();
  const idempotency = useIdempotencyKey();
  const router = useRouter();
  const { refusal, handle, clear } = useOrderRefusal(order.id, onClose);

  const submit = useAsyncAction({
    action: () =>
      remove.mutateAsync({
        id: order.id,
        idempotencyKey: idempotency.keyFor({ id: order.id, delete: true }),
      }),
    logger: log,
    fn: "handleDeleteOrder",
    dataId: "SO-003",
    onSuccess: () => {
      toast.success("Draft deleted", {
        description: `${order.party.name} · its quotations can be ordered again`,
      });
      router.push(order.lead === null ? "/sales-orders" : `/leads/${order.lead.id}`);
    },
    onError: handle,
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        clear();
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Delete this draft?</DialogTitle>
        <DialogDescription>
          {order.party.name} · {formatInr(order.totals.total, { paise: true })}. It was never
          submitted, so nothing else refers to it. A deleted draft can&apos;t be brought back.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <RefusalAlert refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={submit.state}
          loadingLabel="Deleting…"
          successLabel="Deleted"
          errorLabel="Not deleted"
        >
          Delete draft
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── cancel, close short, void: a reason is required (SO-004, DISP-002) ─────────

type RemarkAction = "cancel" | "close-short" | "void";

const REMARK_COPY: Readonly<
  Record<RemarkAction, { title: string; label: string; submit: string; busy: string; done: string }>
> = {
  cancel: {
    title: "Cancel this order?",
    label: "Why is it cancelled?",
    submit: "Cancel order",
    busy: "Cancelling…",
    done: "Cancelled",
  },
  "close-short": {
    title: "Close the order short?",
    label: "Why won't the rest ship?",
    submit: "Close short",
    busy: "Closing…",
    done: "Closed",
  },
  void: {
    title: "Void this dispatch?",
    label: "Why is it void?",
    submit: "Void dispatch",
    busy: "Voiding…",
    done: "Voided",
  },
};

function RemarkForm({
  order,
  action,
  dispatch,
  onClose,
}: FormProps & { action: RemarkAction; dispatch?: Dispatch }): React.JSX.Element {
  const cancel = useCancelOrder();
  const closeShort = useCloseOrderShort();
  const voidDispatch = useVoidDispatch();
  const idempotency = useIdempotencyKey();
  const { refusal, handle, clear } = useOrderRefusal(order.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const copy = REMARK_COPY[action];
  const form = useForm<RequiredRemarkForm>({
    resolver: zodResolver(requiredRemarkFormSchema),
    defaultValues: { remark: "" },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const submit = useAsyncAction({
    action: (remark: string) => {
      const body = { remark, expected_status: order.status };
      const id = action === "void" ? (dispatch?.id ?? "") : order.id;
      const input = { body, idempotencyKey: idempotency.keyFor({ id, action, ...body }) };
      switch (action) {
        case "cancel":
          return cancel.mutateAsync({ id, input });
        case "close-short":
          return closeShort.mutateAsync({ id, input });
        case "void":
          return voidDispatch.mutateAsync({ id, input });
      }
    },
    logger: log,
    fn:
      action === "void"
        ? "handleVoidDispatch"
        : action === "cancel"
          ? "handleCancelOrder"
          : "handleCloseShort",
    dataId: action === "cancel" ? "SO-004" : "DISP-002",
    onSuccess: () => {
      idempotency.reset();
      toast.success(
        action === "void"
          ? `${dispatch?.dispatchNo ?? "Dispatch"} voided`
          : `${orderNumber(order)} ${copy.done.toLowerCase()}`,
        action === "void" ? { description: "Its quantities are open again." } : undefined,
      );
      closeSoon();
    },
    onError: (error) => {
      const message = readFieldErrors(error)?.remark;
      if (message !== undefined) {
        form.setError("remark", { type: "server", message });
      }
      handle(error);
    },
  });

  const explain =
    action === "cancel"
      ? "The order stays on record, marked cancelled, and its quotations can be ordered again. The reason is kept on its history."
      : action === "close-short"
        ? "Every quantity still open becomes short, and nothing more ships against this order. What has left stays as it is."
        : `${dispatch?.dispatchNo ?? "The dispatch"} stays on record, marked void, and its quantities are open again.`;

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        clear();
        void form.handleSubmit((values) => submit.run(values.remark))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>{copy.title}</DialogTitle>
        <DialogDescription>
          {orderNumber(order)} · {order.party.name}. {explain}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <Field data-invalid={errors.remark ? true : undefined}>
          <FieldLabel htmlFor="order-action-remark">{copy.label}</FieldLabel>
          <Textarea
            id="order-action-remark"
            rows={3}
            aria-invalid={errors.remark ? true : undefined}
            aria-describedby={
              errors.remark ? "order-action-remark-error" : "order-action-remark-description"
            }
            {...form.register("remark")}
          />
          {errors.remark ? null : (
            <FieldDescription id="order-action-remark-description">
              Required. Kept on the order and its history.
            </FieldDescription>
          )}
          <FieldError id="order-action-remark-error">{errors.remark?.message}</FieldError>
        </Field>
        <RefusalAlert refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={submit.state}
          loadingLabel={copy.busy}
          successLabel={copy.done}
          errorLabel="Not done"
        >
          {copy.submit}
        </Button>
      </DialogFooter>
    </form>
  );
}
