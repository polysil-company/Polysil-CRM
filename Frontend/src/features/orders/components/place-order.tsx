"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { PackageIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
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
import { orderListQueryOptions } from "@/features/orders/api/orders.queries";
import {
  ORDER_STATUSES,
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
import { isApiError } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { canConsolidate, ConsolidateQuotations } from "./consolidate-quotations";
import { RefusalAlert } from "./order-dialog-shared";

const log = createLogger({ file: "features/orders/components/place-order.tsx", dataId: "SO-003" });

const placeOrderFormSchema = orderHeaderFormSchema.extend({
  orderType: z.enum([...ORDERABLE_TYPES, "subsidised", "export"]),
});
type PlaceOrderForm = z.infer<typeof placeOrderFormSchema>;

/** Every status but cancelled: a cancelled order released its quotations. */
const LIVE_STATUSES = ORDER_STATUSES.filter((status) => status !== "cancelled");

/** The live order that carries this quotation, if any (BE-019). */
function quotationOrderParams(quotationId: string): OrderListParams {
  return {
    cursor: null,
    pageSize: 25,
    q: "",
    status: LIVE_STATUSES,
    orderType: null,
    mine: false,
    leadId: null,
    quotationId,
    areas: [],
    officeId: null,
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
  const orders = useQuery({
    ...orderListQueryOptions(quotationOrderParams(quotation.id)),
    enabled: orderable,
  });
  const [open, setOpen] = useState(false);

  if (!orderable) {
    return null;
  }
  // Each accepted quotation goes on one live order, so the first row is the one.
  const existing = orders.data?.items[0];
  const checking = orders.isPending;
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

const takenSchema = z.object({ fields: z.object({ quotation_ids: z.string() }) });

/** SO-011 · The quotation a `quotation_on_order` refusal names, if any. */
function takenQuotationId(error: unknown): string | null {
  if (!isApiError(error) || error.code !== "quotation_on_order") return null;
  return takenSchema.safeParse(error.details).data?.fields.quotation_ids ?? null;
}

/** The draft's type and header; on success the new order's page opens. */
function PlaceOrderForm({ quotation }: { quotation: Quotation }): React.JSX.Element {
  const create = useCreateOrder();
  const idempotency = useIdempotencyKey();
  const router = useRouter();
  const [refusal, setRefusal] = useState<OrderRefusal | null>(null);
  // SO-011 · The dealer's other quotations ticked to join this one, and those found on an order.
  const [others, setOthers] = useState<string[]>([]);
  const [onOrder, setOnOrder] = useState<string[]>([]);
  // SO-008 · A subsidised quotation makes a subsidised order, its subsidy with it (FS-057).
  const subsidised = quotation.salesType === "subsidised";
  // SO-010 · An export quotation makes an export order, and only an export one (type_mismatch).
  const exported = quotation.salesType === "export";
  const fixedType = subsidised ? "subsidised" : exported ? "export" : null;
  const defaultType =
    fixedType ?? ORDERABLE_TYPES.find((type) => type === quotation.salesType) ?? "commercial";
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
        quotation_ids: [quotation.id, ...others],
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
      // SO-011 · A ticked quotation already on an order is unticked and marked, so a retry works.
      const taken = takenQuotationId(error);
      if (taken !== null && others.includes(taken)) {
        setOthers((current) => current.filter((id) => id !== taken));
        setOnOrder((current) => [...current, taken]);
        setRefusal({
          title: "One of the added quotations is on an order already",
          message:
            "It is now unticked and marked. Make the order without it, or tick another quotation.",
          stale: false,
        });
        return;
      }
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
          {formatInr(quotation.totals.total, { paise: true })}
          {others.length > 0
            ? `, and ${String(others.length)} more quotation${others.length === 1 ? "" : "s"}`
            : ""}
          . The items and prices come from the quotation{others.length > 0 ? "s" : ""}. The order
          starts as a draft.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <div className="flex flex-col gap-4">
          {fixedType !== null ? (
            <Field>
              <FieldLabel>Order type</FieldLabel>
              <p className="text-sm text-foreground">{ORDER_TYPE_LABELS[fixedType]}</p>
              <FieldDescription>
                {exported
                  ? `An export quotation makes an export order${quotation.exportCountry === null ? "" : ` to ${quotation.exportCountry}`}, taxed as the quotation is.`
                  : quotation.subsidy === null
                    ? "The quotation has no subsidy yet."
                    : `The subsidy comes from the quotation: ${formatInr(quotation.subsidy.subsidy, { paise: true })} from the scheme, ${formatInr(quotation.subsidy.farmerShare, { paise: true })} from the farmer.`}
              </FieldDescription>
            </Field>
          ) : (
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
              <FieldDescription>
                A sample is typed in on a new order; an export comes from an export quotation.
              </FieldDescription>
            </Field>
          )}
          {canConsolidate(quotation) ? (
            <ConsolidateQuotations
              quotation={quotation}
              selected={others}
              onSelectedChange={(next) => {
                setRefusal(null);
                setOthers(next);
              }}
              onOrder={onOrder}
              disabled={submit.isBusy}
            />
          ) : null}
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
