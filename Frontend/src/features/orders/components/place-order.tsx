"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { PackageIcon } from "@hugeicons/core-free-icons";
import { useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { useForm, useFormState, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
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
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { useCreateOrder } from "@/features/orders/api/orders.mutations";
import {
  orderDetailQueryOptions,
  orderListQueryOptions,
} from "@/features/orders/api/orders.queries";
import {
  ORDERABLE_TYPES,
  PAYMENT_TERMS,
  orderHeaderFormSchema,
  type OrderListParams,
} from "@/features/orders/api/orders.schemas";
import {
  ORDER_TYPE_LABELS,
  PAYMENT_TERMS_LABELS,
  orderNumber,
} from "@/features/orders/lib/order-labels";
import { orderRefusal, type OrderRefusal } from "@/features/orders/lib/order-lifecycle";
import type { Quotation } from "@/features/quotations/api/quotations.schemas";
import { quotationTitle } from "@/features/quotations/lib/quotation-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { RefusalAlert } from "./order-dialog-shared";

const log = createLogger({ file: "features/orders/components/place-order.tsx", dataId: "SO-003" });

const placeOrderFormSchema = orderHeaderFormSchema.extend({
  orderType: z.enum(ORDERABLE_TYPES),
});
type PlaceOrderForm = z.infer<typeof placeOrderFormSchema>;

/** How many of the lead's live orders are read to find the one carrying this quotation. */
const MAX_ORDERS_CHECKED = 10;

/** A lead's orders: enough to find the one that already carries a quotation. */
function leadOrdersParams(leadId: string): OrderListParams {
  return {
    cursor: null,
    pageSize: 100,
    q: "",
    status: [],
    orderType: null,
    mine: false,
    leadId,
  };
}

/**
 * SO-003 · On an accepted, current quotation: "Place order" makes a draft order from it, or
 * — when a live order already carries it — "Open order" goes there. Shown to those who may
 * create orders; the backend checks the rest.
 */
export function PlaceOrder({ quotation }: { quotation: Quotation }): React.JSX.Element | null {
  const canCreate = useCan("sales_orders", "create");
  const orderable = canCreate && quotation.status === "accepted" && quotation.supersededBy === null;
  const leadId = quotation.lead?.id ?? null;
  const orders = useQuery({
    ...orderListQueryOptions(leadOrdersParams(leadId ?? "")),
    enabled: orderable && leadId !== null,
  });
  // The list row has no quotation ids, so each live order of the lead is read to find it.
  // TODO(SO-003): one `GET /orders?quotation_id=` call once the backend has it (BE-019).
  const live = (orders.data?.items ?? [])
    .filter((order) => order.status !== "cancelled")
    .slice(0, MAX_ORDERS_CHECKED);
  const details = useQueries({
    queries: live.map((order) => ({ ...orderDetailQueryOptions(order.id), enabled: orderable })),
  });
  const [open, setOpen] = useState(false);

  if (!orderable) {
    return null;
  }
  const existing = details
    .map((detail) => detail.data)
    .find((order) => order?.quotations.some((item) => item.id === quotation.id) === true);
  const checking =
    leadId !== null && (orders.isPending || details.some((detail) => detail.isPending));
  if (existing !== undefined) {
    return (
      <Link
        href={`/sales-orders/${existing.id}`}
        transitionTypes={["nav-forward"]}
        className={buttonVariants({ variant: "outline" })}
      >
        <Icon icon={PackageIcon} />
        Open order {existing.orderNo ?? "(draft)"}
      </Link>
    );
  }

  return (
    <>
      <Button
        disabled={checking}
        onClick={() => {
          setOpen(true);
        }}
      >
        <Icon icon={PackageIcon} />
        Place order
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent size="sm">
          {open ? <PlaceOrderForm quotation={quotation} /> : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** The draft's type and header; on success the new order's page opens. */
function PlaceOrderForm({ quotation }: { quotation: Quotation }): React.JSX.Element {
  const create = useCreateOrder();
  const idempotency = useIdempotencyKey();
  const router = useRouter();
  const [refusal, setRefusal] = useState<OrderRefusal | null>(null);
  const defaultType = ORDERABLE_TYPES.find((type) => type === quotation.salesType) ?? "commercial";
  const form = useForm<PlaceOrderForm>({
    resolver: zodResolver(placeOrderFormSchema),
    defaultValues: {
      orderType: defaultType,
      deliveryAddress: quotation.party.address ?? "",
      paymentTerms: "full_payment",
      remarks: "",
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const [orderType, paymentTerms] = useWatch({
    control: form.control,
    name: ["orderType", "paymentTerms"],
  });

  const submit = useAsyncAction({
    action: (values: PlaceOrderForm) => {
      const body = {
        order_type: values.orderType,
        quotation_ids: [quotation.id],
        delivery_address: values.deliveryAddress === "" ? null : values.deliveryAddress,
        payment_terms: values.paymentTerms,
        remarks: values.remarks === "" ? null : values.remarks,
      };
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handlePlaceOrder",
    dataId: "SO-003",
    onSuccess: (order) => {
      idempotency.reset();
      toast.success("Draft order made", {
        description: `${orderNumber(order)} · check it, then submit it for approval`,
      });
      router.push(`/sales-orders/${order.id}`);
    },
    onError: (error) => {
      setRefusal(orderRefusal(error));
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => submit.run(values))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Place an order</DialogTitle>
        <DialogDescription>
          From {quotationTitle(quotation)} · {quotation.party.name} ·{" "}
          {formatInr(quotation.totals.total, { paise: true })}. The items and prices come from the
          quotation. The order starts as a draft.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <div className="flex flex-col gap-4">
          <Field>
            <FieldLabel id="place-order-type-label">Order type</FieldLabel>
            <RadioGroup
              aria-labelledby="place-order-type-label"
              value={orderType}
              onValueChange={(value) => {
                const type = ORDERABLE_TYPES.find((item) => item === value);
                if (type !== undefined) {
                  form.setValue("orderType", type, { shouldDirty: true });
                }
              }}
              className="flex flex-wrap gap-4"
            >
              {ORDERABLE_TYPES.map((type) => (
                <div key={type} className="flex items-center gap-2">
                  <RadioGroupItem id={`place-order-type-${type}`} value={type} />
                  <Label htmlFor={`place-order-type-${type}`} className="font-normal">
                    {ORDER_TYPE_LABELS[type]}
                  </Label>
                </div>
              ))}
            </RadioGroup>
            <FieldDescription>Export, sample and the other types come later.</FieldDescription>
          </Field>
          <Field data-invalid={errors.deliveryAddress ? true : undefined}>
            <FieldLabel htmlFor="place-order-address">Deliver to</FieldLabel>
            <Textarea
              id="place-order-address"
              rows={3}
              aria-invalid={errors.deliveryAddress ? true : undefined}
              aria-describedby={errors.deliveryAddress ? "place-order-address-error" : undefined}
              {...form.register("deliveryAddress")}
            />
            <FieldError id="place-order-address-error">
              {errors.deliveryAddress?.message}
            </FieldError>
          </Field>
          <Field>
            <FieldLabel id="place-order-terms-label">Payment terms</FieldLabel>
            <RadioGroup
              aria-labelledby="place-order-terms-label"
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
                  <RadioGroupItem id={`place-order-terms-${terms}`} value={terms} />
                  <Label htmlFor={`place-order-terms-${terms}`} className="font-normal">
                    {PAYMENT_TERMS_LABELS[terms]}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </Field>
          <Field data-invalid={errors.remarks ? true : undefined}>
            <FieldLabel htmlFor="place-order-remarks">
              Remarks <span className="font-normal text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="place-order-remarks"
              rows={2}
              aria-invalid={errors.remarks ? true : undefined}
              aria-describedby={errors.remarks ? "place-order-remarks-error" : undefined}
              {...form.register("remarks")}
            />
            <FieldError id="place-order-remarks-error">{errors.remarks?.message}</FieldError>
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
          loadingLabel="Making…"
          successLabel="Made"
          errorLabel="Not made"
        >
          Make draft order
        </Button>
      </DialogFooter>
    </form>
  );
}
