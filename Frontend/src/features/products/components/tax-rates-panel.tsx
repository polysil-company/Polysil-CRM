"use client";

import { Add01Icon, Invoice03Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { PRODUCT_PAGE_SIZE } from "@/features/products/api/products.api";
import { useSetTaxRate } from "@/features/products/api/products.mutations";
import { taxRateListQueryOptions } from "@/features/products/api/products.queries";
import { GST_SLABS, type TaxRate } from "@/features/products/api/products.schemas";
import { Pager } from "@/features/products/components/pager";
import { dayText, slabText, windowOf } from "@/features/products/lib/product-labels";
import { readRefusal } from "@/features/products/lib/refusals";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatCount, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/products/components/tax-rates-panel.tsx",
  dataId: "MSTR-005",
});

const HSN_PATTERN = /^\d{4,8}$/;
const SLAB_ITEMS = GST_SLABS.map((value) => ({ value, label: slabText(value) }));

/**
 * MSTR-005 · GST by HSN code: each code's slab from a date, so a Council change is entered once
 * and reaches every product under the code. A rate set for a later date waits its turn; the one
 * in force closes the day before.
 */
export function TaxRatesPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const [hsn, setHsn] = useState("");
  const [inForce, setInForce] = useState(true);
  const [page, setPage] = useState(1);
  const [setting, setSetting] = useState<string | null>(null);
  const hsnFilter = HSN_PATTERN.test(hsn) ? hsn : null;
  const query = useQuery(taxRateListQueryOptions(hsnFilter, inForce, page));

  return (
    <section aria-label="Tax rates" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Find an HSN code"
          placeholder="HSN code, 4 to 8 digits"
          value={hsn}
          onSearch={(next) => {
            setHsn(next);
            setPage(1);
          }}
        />
        <div className="flex items-center gap-2 px-1">
          <Checkbox
            id="tax-in-force"
            checked={inForce}
            onCheckedChange={(checked) => {
              setInForce(checked);
              setPage(1);
            }}
          />
          <Label htmlFor="tax-in-force" className="text-sm">
            In force today only
          </Label>
        </div>
        {canEdit ? (
          <Button
            className="md:ml-auto"
            onClick={() => {
              setSetting(hsnFilter ?? "");
            }}
          >
            <Icon icon={Add01Icon} />
            Set a rate
          </Button>
        ) : null}
      </div>
      {hsn !== "" && hsnFilter === null ? (
        <p role="status" className="text-sm text-warning">
          An HSN code is 4 to 8 digits: showing every code until it is one.
        </p>
      ) : null}

      <QueryView
        query={query}
        pending={<TaxRatesSkeleton />}
        isEmpty={(data) => data.total === 0}
        empty={
          <EmptyState
            icon={Invoice03Icon}
            title={hsnFilter === null ? "No GST rates yet" : `No rate for HSN ${hsnFilter}`}
            description={
              canEdit
                ? "Set the slab for a code: every product under it is taxed at it from that day."
                : "Admin-Sales sets the GST slab for each HSN code."
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <p aria-live="polite" className="text-sm text-muted-foreground">
              {formatCount(data.total)} {data.total === 1 ? "rate" : "rates"}
              {inForce ? " in force today" : ", past and future included"}.
            </p>
            <ul aria-label="GST rates" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {data.items.map((rate) => (
                <TaxRateRow
                  key={rate.id}
                  rate={rate}
                  canEdit={canEdit}
                  onChange={() => {
                    setSetting(rate.hsnCode);
                  }}
                />
              ))}
            </ul>
            <Pager
              page={page}
              limit={PRODUCT_PAGE_SIZE}
              total={data.total}
              noun="rates"
              isPaging={query.isPlaceholderData}
              onPage={setPage}
            />
          </div>
        )}
      </QueryView>

      <Dialog
        open={setting !== null}
        onOpenChange={(open) => {
          if (!open) setSetting(null);
        }}
      >
        <DialogContent size="sm">
          {setting === null ? null : (
            <SetRateForm
              initialHsn={setting}
              onClose={() => {
                setSetting(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function TaxRateRow({
  rate,
  canEdit,
  onChange,
}: {
  rate: TaxRate;
  canEdit: boolean;
  onChange: () => void;
}): React.JSX.Element {
  const today = todayInIndia();
  const future = rate.from > today;
  const ended = rate.to !== null && rate.to <= today;
  return (
    <li className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-foreground">
            HSN {rate.hsnCode}
          </span>
          <Badge variant="info" size="sm">
            GST {slabText(rate.rate)}
          </Badge>
          {future ? (
            <Badge variant="warning" size="sm">
              Starts later
            </Badge>
          ) : ended ? (
            <Badge variant="neutral" size="sm">
              Ended
            </Badge>
          ) : null}
        </p>
        <p className="text-xs text-muted-foreground">{windowOf(rate.from, rate.to)}</p>
      </div>
      {canEdit && !ended ? (
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Change the rate for HSN ${rate.hsnCode}`}
          onClick={onChange}
        >
          Change
        </Button>
      ) : null}
    </li>
  );
}

function SetRateForm({
  initialHsn,
  onClose,
}: {
  initialHsn: string;
  onClose: () => void;
}): React.JSX.Element {
  const setRate = useSetTaxRate();
  const idempotency = useIdempotencyKey();
  const [hsn, setHsn] = useState(initialHsn);
  const [slab, setSlab] = useState<string | null>(null);
  const [from, setFrom] = useState(todayInIndia);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems = {
    hsn: HSN_PATTERN.test(hsn.trim()) ? null : "Four to eight digits.",
    slab: slab === null ? "Choose the slab." : null,
    from: /^\d{4}-\d{2}-\d{2}$/.test(from) ? null : "Choose the day it starts.",
  };

  const submit = useAsyncAction({
    action: () => {
      const request = { hsnCode: hsn.trim(), rate: slab ?? "", from };
      return setRate.mutateAsync({ ...request, idempotencyKey: idempotency.keyFor(request) });
    },
    logger: log,
    fn: "handleSetTaxRate",
    dataId: "MSTR-005",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`HSN ${hsn.trim()}: GST ${slabText(slab ?? "0")}`, {
        description: `From ${dayText(from)}, for every product under the code.`,
      });
      onClose();
    },
    onError: (error) => {
      const read = readRefusal(error, { rate: "slab", effective_from: "from", hsn_code: "hsn" });
      setRefusal(read.message ?? Object.values(read.fields).join(" "));
    },
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>Set a GST rate</DialogTitle>
        <DialogDescription>
          From the day you choose, every product under the code is taxed at this slab. The rate
          before it ends the day before.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <form
          id="tax-rate-form"
          noValidate
          aria-label="Set a GST rate"
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            setShown(true);
            setRefusal(null);
            if (Object.values(problems).some((problem) => problem !== null)) return;
            void submit.run();
          }}
        >
          <Field data-invalid={shown && problems.hsn !== null ? true : undefined}>
            <FieldLabel htmlFor="tax-hsn">HSN code</FieldLabel>
            <Input
              id="tax-hsn"
              inputMode="numeric"
              autoComplete="off"
              maxLength={8}
              className="font-mono"
              value={hsn}
              aria-invalid={shown && problems.hsn !== null ? true : undefined}
              aria-describedby={shown && problems.hsn !== null ? "tax-hsn-error" : undefined}
              onChange={(event) => {
                setHsn(event.target.value);
              }}
            />
            <FieldError id="tax-hsn-error">{shown ? problems.hsn : null}</FieldError>
          </Field>
          <Field data-invalid={shown && problems.slab !== null ? true : undefined}>
            <FieldLabel htmlFor="tax-slab">GST slab</FieldLabel>
            <Select
              items={SLAB_ITEMS}
              value={slab}
              onValueChange={(next) => {
                setSlab(typeof next === "string" ? next : null);
              }}
            >
              <SelectTrigger
                id="tax-slab"
                className="w-full"
                aria-invalid={shown && problems.slab !== null ? true : undefined}
                aria-describedby={
                  shown && problems.slab !== null ? "tax-slab-error" : "tax-slab-help"
                }
              >
                <SelectValue placeholder="Choose a slab" />
              </SelectTrigger>
              <SelectContent>
                {SLAB_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {shown && problems.slab !== null ? null : (
              <FieldDescription id="tax-slab-help">
                The slabs the GST Council uses.
              </FieldDescription>
            )}
            <FieldError id="tax-slab-error">{shown ? problems.slab : null}</FieldError>
          </Field>
          <Field data-invalid={shown && problems.from !== null ? true : undefined}>
            <FieldLabel htmlFor="tax-from">From</FieldLabel>
            <Input
              id="tax-from"
              type="date"
              value={from}
              onChange={(event) => {
                setFrom(event.target.value);
              }}
            />
            <FieldError>{shown ? problems.from : null}</FieldError>
          </Field>
          {refusal === null ? null : (
            <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
              {refusal}
            </p>
          )}
        </form>
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          form="tax-rate-form"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Set the rate
        </Button>
      </DialogFooter>
    </>
  );
}

function TaxRatesSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading tax rates"
      className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3"
    >
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border border-border p-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-32" />
        </div>
      ))}
    </div>
  );
}
