"use client";

import {
  Add01Icon,
  Cancel01Icon,
  MinusSignIcon,
  ShoppingBasket01Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCreateMarketingOrder } from "@/features/marketing/api/marketing.mutations";
import { materialsQueryOptions } from "@/features/marketing/api/marketing.queries";
import type { MarketingOrder, Material } from "@/features/marketing/api/marketing.schemas";
import { percentText, previewShares } from "@/features/marketing/lib/marketing-labels";
import { PartnerSearchPicker } from "@/features/schemes/components/record-pickers";
import { useIsStaff } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/marketing/components/order-material.tsx",
  dataId: "MKT-003",
});

/** A sensible ceiling per line; the backend takes any whole number. */
const MAX_QTY = 9999;

type Basket = Readonly<Record<string, number>>;

/**
 * MKT-003 · Order marketing material: the catalogue as cards with Add and a quantity, and a
 * basket showing the value split between the company and the dealer. A dealer orders for itself;
 * staff pick the dealer, or leave it empty for their office's own use (the company pays all).
 * The order goes straight to the District Manager; there is no draft.
 */
export function OrderMaterial({
  onPlaced,
}: {
  onPlaced: (order: MarketingOrder) => void;
}): React.JSX.Element {
  const query = useQuery(materialsQueryOptions(true));
  const [basket, setBasket] = useState<Basket>({});

  const setQty = (materialId: string, qty: number): void => {
    const next: Record<string, number> = { ...basket };
    if (qty <= 0) delete next[materialId];
    else next[materialId] = Math.min(MAX_QTY, qty);
    setBasket(next);
  };

  if (query.status === "pending") {
    return (
      <div
        aria-busy="true"
        aria-label="Loading the catalogue"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
      >
        {[0, 1, 2, 3, 4, 5].map((card) => (
          <Skeleton key={card} className="h-36 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (query.status === "error") {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  const offered = query.data.filter((material) => material.price !== null);
  if (offered.length === 0) {
    return (
      <EmptyState
        icon={ShoppingBasket01Icon}
        title="Nothing to order yet"
        description="The marketing team adds items and their prices to the catalogue."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }

  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <ul aria-label="Catalogue" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {offered.map((material) => (
          <MaterialCard
            key={material.id}
            material={material}
            qty={basket[material.id] ?? 0}
            onQty={(qty) => {
              setQty(material.id, qty);
            }}
          />
        ))}
      </ul>
      <BasketPanel
        materials={offered}
        basket={basket}
        onQty={setQty}
        onPlaced={(order) => {
          setBasket({});
          onPlaced(order);
        }}
      />
    </div>
  );
}

function MaterialCard({
  material,
  qty,
  onQty,
}: {
  material: Material;
  qty: number;
  onQty: (qty: number) => void;
}): React.JSX.Element {
  const inputId = `qty-${material.id}`;
  return (
    <li
      className={cn(
        "flex flex-col justify-between gap-3 rounded-xl border bg-card p-4 transition-colors duration-fast ease-out",
        qty > 0 ? "border-primary" : "border-border",
      )}
    >
      <div className="flex flex-col gap-1">
        <span className="font-mono text-xs text-muted-foreground">{material.code}</span>
        <span className="text-sm font-semibold text-foreground">{material.name}</span>
        <span className="flex flex-wrap items-center gap-2 text-sm text-foreground tabular-nums">
          {formatInr(material.price, { paise: true })} / {material.unit}
          {material.provisional ? (
            <Badge variant="outline" size="sm">
              Indicative
            </Badge>
          ) : null}
        </span>
        <span className="text-xs text-muted-foreground">
          Company pays {percentText(material.companySharePct)}
        </span>
      </div>
      {qty === 0 ? (
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          aria-label={`Add ${material.name}`}
          onClick={() => {
            onQty(1);
          }}
        >
          <Icon icon={Add01Icon} />
          Add
        </Button>
      ) : (
        <QtyStepper id={inputId} name={material.name} qty={qty} onQty={onQty} />
      )}
    </li>
  );
}

function QtyStepper({
  id,
  name,
  qty,
  onQty,
}: {
  id: string;
  name: string;
  qty: number;
  onQty: (qty: number) => void;
}): React.JSX.Element {
  return (
    <div role="group" aria-label={`How many ${name}`} className="flex items-center gap-1.5">
      <Button
        variant="outline"
        size="icon-sm"
        aria-label={qty === 1 ? `Remove ${name}` : `One fewer ${name}`}
        onClick={() => {
          onQty(qty - 1);
        }}
      >
        <Icon icon={MinusSignIcon} />
      </Button>
      <Input
        id={id}
        aria-label={`Quantity of ${name}`}
        inputMode="numeric"
        autoComplete="off"
        className="h-control-sm w-20 text-center tabular-nums"
        value={String(qty)}
        onChange={(event) => {
          const digits = event.target.value.replace(/\D/g, "");
          onQty(digits === "" ? 0 : Number(digits));
        }}
      />
      <Button
        variant="outline"
        size="icon-sm"
        aria-label={`One more ${name}`}
        disabled={qty >= MAX_QTY}
        onClick={() => {
          onQty(qty + 1);
        }}
      >
        <Icon icon={Add01Icon} />
      </Button>
    </div>
  );
}

function BasketPanel({
  materials,
  basket,
  onQty,
  onPlaced,
}: {
  materials: readonly Material[];
  basket: Basket;
  onQty: (materialId: string, qty: number) => void;
  onPlaced: (order: MarketingOrder) => void;
}): React.JSX.Element {
  const staff = useIsStaff();
  const create = useCreateMarketingOrder();
  const idempotency = useIdempotencyKey();
  const [dealer, setDealer] = useState<{ id: string; name: string } | null>(null);
  const [remark, setRemark] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const chosen = materials.filter((material) => (basket[material.id] ?? 0) > 0);
  const officeUse = staff && dealer === null;
  const shares = previewShares(basket, materials, officeUse);
  const provisional = chosen.some((material) => material.provisional);

  const submit = useAsyncAction({
    action: () => {
      const body = {
        partner_id: staff ? (dealer?.id ?? null) : null,
        lines: chosen.map((material) => ({
          material_id: material.id,
          qty: basket[material.id] ?? 0,
        })),
        remark: remark.trim() === "" ? null : remark.trim(),
      };
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handlePlaceMarketingOrder",
    dataId: "MKT-003",
    onSuccess: (order) => {
      idempotency.reset();
      setRemark("");
      setDealer(null);
      toast.success(`Order ${order.orderNo} placed`, {
        description: "It has gone to the District Manager for approval.",
      });
      onPlaced(order);
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "material_inactive"
          ? "An item was taken off the catalogue. Remove it and try again."
          : toUserFacingError(error).title,
      );
    },
  });

  return (
    <section
      aria-labelledby="basket-title"
      className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 lg:sticky lg:top-4"
    >
      <h2
        id="basket-title"
        className="flex items-center gap-2 text-base font-semibold text-foreground"
      >
        <Icon icon={ShoppingBasket01Icon} className="text-muted-foreground" />
        Your order
      </h2>

      {staff ? (
        <Field>
          <FieldLabel htmlFor="marketing-dealer">For a dealer</FieldLabel>
          {dealer === null ? (
            <PartnerSearchPicker
              id="marketing-dealer"
              placeholder="Search a dealer, or leave empty"
              aria-describedby="marketing-dealer-help"
              onPick={(picked) => {
                setDealer({ id: picked.id, name: picked.name });
              }}
            />
          ) : (
            <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <span className="text-foreground">{dealer.name}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Not for ${dealer.name}: order for the office`}
                onClick={() => {
                  setDealer(null);
                }}
              >
                <Icon icon={Cancel01Icon} />
              </Button>
            </div>
          )}
          <FieldDescription id="marketing-dealer-help">
            {dealer === null
              ? "Empty: for your office's own use, and the company pays all of it."
              : "The dealer pays its share of each item."}
          </FieldDescription>
        </Field>
      ) : null}

      {chosen.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
          Add items from the catalogue.
        </p>
      ) : (
        <ul aria-label="Items in your order" className="flex flex-col divide-y divide-border">
          {chosen.map((material) => (
            <li key={material.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <span className="min-w-0">
                <span className="block truncate text-foreground">{material.name}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {basket[material.id] ?? 0} × {formatInr(material.price, { paise: true })}
                </span>
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${material.name}`}
                onClick={() => {
                  onQty(material.id, 0);
                }}
              >
                <Icon icon={Cancel01Icon} />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <dl aria-label="What it costs" className="grid grid-cols-3 gap-2 text-sm">
        {[
          { term: "Value", value: shares.value },
          { term: "Company pays", value: shares.companyShare },
          { term: officeUse ? "Dealer pays" : "Dealer pays", value: shares.dealerShare },
        ].map((row) => (
          <div key={row.term} className="flex flex-col gap-0.5 rounded-lg bg-muted p-2">
            <dt className="text-xs text-muted-foreground">{row.term}</dt>
            <dd className="font-semibold text-foreground tabular-nums">
              {formatInr(row.value, { paise: true })}
            </dd>
          </div>
        ))}
      </dl>
      {provisional ? (
        <p className="text-xs text-muted-foreground">
          Some prices are indicative: the order keeps the prices in force when it is placed.
        </p>
      ) : null}

      <Field>
        <FieldLabel htmlFor="marketing-remark">Remark (optional)</FieldLabel>
        <Textarea
          id="marketing-remark"
          rows={2}
          maxLength={500}
          placeholder="For the Anand farmer meet"
          value={remark}
          onChange={(event) => {
            setRemark(event.target.value);
          }}
        />
      </Field>

      {refusal === null ? null : (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
          {refusal}
        </p>
      )}

      <Button
        disabled={chosen.length === 0}
        state={submit.state}
        loadingLabel="Placing…"
        successLabel="Placed"
        errorLabel="Not placed"
        onClick={() => {
          setRefusal(null);
          void submit.run();
        }}
      >
        Place order
      </Button>
    </section>
  );
}
