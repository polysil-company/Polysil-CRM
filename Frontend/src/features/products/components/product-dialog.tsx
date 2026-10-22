"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useAssignHsn,
  useCreateProduct,
  usePatchProduct,
} from "@/features/products/api/products.mutations";
import {
  catalogueFacetsQueryOptions,
  hsnHistoryQueryOptions,
} from "@/features/products/api/products.queries";
import {
  QUOTATION_CATEGORIES,
  type CreateProductRequest,
  type PatchProductRequest,
  type Product,
  type QuotationCategory,
} from "@/features/products/api/products.schemas";
import {
  dayText,
  PROVISIONAL_LABELS,
  QUOTATION_CATEGORY_LABELS,
  slabText,
} from "@/features/products/lib/product-labels";
import { readRefusal } from "@/features/products/lib/refusals";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/products/components/product-dialog.tsx",
  dataId: "MSTR-004",
});

const FIELD_NAMES: Readonly<Record<string, string>> = {
  description: "description",
  product_category: "category",
  quotation_category: "quotationCategory",
  uom: "uom",
  item_code: "itemCode",
  mrp: "mrp",
  pack_multiple: "packMultiple",
};

interface Draft {
  description: string;
  itemCode: string;
  category: string | null;
  quotationCategory: QuotationCategory;
  uom: string | null;
  mrp: string;
  packMultiple: string;
  subsidyEligible: boolean;
  /** A new product's first HSN code, set right after it is created (MSTR-005). */
  hsn: string;
  hsnFrom: string;
}

function draftOf(product: Product | null): Draft {
  return {
    description: product?.description ?? "",
    itemCode: product?.itemCode ?? "",
    category: product?.category ?? null,
    quotationCategory: product?.quotationCategory ?? "field",
    uom: product?.uom ?? null,
    mrp: product?.mrp ?? "",
    packMultiple: product?.packMultiple ?? "",
    subsidyEligible: product?.subsidyEligible ?? true,
    hsn: "",
    hsnFrom: todayInIndia(),
  };
}

const POSITIVE = /^\d+(\.\d+)?$/;

const HSN = /^\d{4,8}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

function problemsOf(draft: Draft, creating: boolean): Record<string, string> {
  const problems: Record<string, string> = {};
  if (draft.description.trim() === "")
    problems.description = "Describe it as it prints on a quotation.";
  if (draft.category === null) problems.category = "Choose its category.";
  if (draft.uom === null) problems.uom = "Choose its unit.";
  for (const [key, value] of [
    ["mrp", draft.mrp],
    ["packMultiple", draft.packMultiple],
  ] as const) {
    const trimmed = value.trim();
    if (trimmed !== "" && (!POSITIVE.test(trimmed) || Number(trimmed) <= 0)) {
      problems[key] = "A positive number, or leave it empty.";
    }
  }
  if (creating && draft.hsn.trim() !== "") {
    if (!HSN.test(draft.hsn.trim())) problems.hsn = "Four to eight digits, or leave it empty.";
    if (!DAY.test(draft.hsnFrom)) problems.hsnFrom = "Choose the day it starts.";
  }
  return problems;
}

function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** PATCH body: only what changed. Sending a figure confirms it as the client's own. */
function patchOf(draft: Draft, product: Product): PatchProductRequest {
  return {
    ...(draft.description.trim() === product.description
      ? {}
      : { description: draft.description.trim() }),
    ...(orNull(draft.itemCode) === product.itemCode ? {} : { item_code: orNull(draft.itemCode) }),
    ...(draft.category === null || draft.category === product.category
      ? {}
      : { product_category: draft.category }),
    ...(draft.quotationCategory === product.quotationCategory
      ? {}
      : { quotation_category: draft.quotationCategory }),
    ...(draft.uom === null || draft.uom === product.uom ? {} : { uom: draft.uom }),
    ...(orNull(draft.mrp) === product.mrp ? {} : { mrp: orNull(draft.mrp) }),
    ...(orNull(draft.packMultiple) === product.packMultiple
      ? {}
      : { pack_multiple: orNull(draft.packMultiple) }),
    ...(draft.subsidyEligible === product.subsidyEligible
      ? {}
      : { is_subsidy_eligible: draft.subsidyEligible }),
  };
}

function createOf(draft: Draft): CreateProductRequest {
  return {
    description: draft.description.trim(),
    product_category: draft.category ?? "",
    quotation_category: draft.quotationCategory,
    uom: draft.uom ?? "",
    item_code: orNull(draft.itemCode),
    mrp: orNull(draft.mrp),
    pack_multiple: orNull(draft.packMultiple),
    is_subsidy_eligible: draft.subsidyEligible,
  };
}

/** "Stand-in" beside a figure the backend still holds as its own guess. */
function StandIn({ show }: { show: boolean }): React.JSX.Element | null {
  return show ? (
    <Badge variant="warning" className="ml-1.5 align-middle">
      Stand-in
    </Badge>
  ) : null;
}

/**
 * MSTR-004 · Add a product, or correct one. The category and unit are the catalogue's own
 * (no endpoint lists them yet, BE-024); a description already in use is refused. Editing, the
 * tax heading follows (MSTR-005), and the product can be switched off or on.
 */
export function ProductDialog({
  product,
  canEdit,
  onClose,
}: {
  product: Product | null;
  canEdit: boolean;
  onClose: () => void;
}): React.JSX.Element {
  const facets = useQuery(catalogueFacetsQueryOptions());
  const create = useCreateProduct();
  const patch = usePatchProduct();
  const assign = useAssignHsn();
  const idempotency = useIdempotencyKey();
  const hsnIdempotency = useIdempotencyKey();
  // A new product whose HSN didn't take stays open here, as the product it now is.
  const [created, setCreated] = useState<Product | null>(null);
  const current = created ?? product;
  const [draft, setDraft] = useState<Draft>(() => draftOf(product));
  const [shown, setShown] = useState(false);
  const [serverFields, setServerFields] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const problems = problemsOf(draft, current === null);
  const errors: Record<string, string | undefined> = shown
    ? { ...serverFields, ...problems }
    : serverFields;
  const body = current === null ? null : patchOf(draft, current);
  const nothing = body !== null && Object.keys(body).length === 0;
  const set = (patchDraft: Partial<Draft>): void => {
    setDraft((current) => ({ ...current, ...patchDraft }));
    setServerFields({});
  };

  const submit = useAsyncAction({
    action: async (): Promise<{ saved: Product; hsnError: unknown }> => {
      if (current === null) {
        const request = createOf(draft);
        const saved = await create.mutateAsync({
          body: request,
          idempotencyKey: idempotency.keyFor(request),
        });
        const hsnCode = draft.hsn.trim();
        if (hsnCode === "") return { saved, hsnError: null };
        // A separate request with its own key: the product stays made whatever this answers.
        const hsnRequest = { productId: saved.id, hsnCode, from: draft.hsnFrom };
        try {
          await assign.mutateAsync({
            ...hsnRequest,
            idempotencyKey: hsnIdempotency.keyFor(hsnRequest),
          });
          return { saved, hsnError: null };
        } catch (error) {
          return { saved, hsnError: error };
        }
      }
      const request = body ?? {};
      const saved = await patch.mutateAsync({
        productId: current.id,
        body: request,
        idempotencyKey: idempotency.keyFor(request),
      });
      return { saved, hsnError: null };
    },
    logger: log,
    fn: current === null ? "handleCreateProduct" : "handleEditProduct",
    dataId: "MSTR-004",
    onSuccess: ({ saved, hsnError }) => {
      idempotency.reset();
      hsnIdempotency.reset();
      if (hsnError !== null) {
        const read = readRefusal(hsnError, { hsn_code: "hsn", effective_from: "hsnFrom" });
        const reason =
          read.message ?? (Object.values(read.fields).join(" ") || "the code was refused.");
        toast.error(`Product added, HSN not set: ${reason}`);
        // Stay open on the new product, so its tax heading can be set below.
        setCreated(saved);
        setDraft(draftOf(saved));
        setShown(false);
        return;
      }
      toast.success(current === null ? "Product added" : "Product saved", {
        description: saved.description,
      });
      onClose();
    },
    onError: (error) => {
      const read = readRefusal(error, FIELD_NAMES);
      setServerFields(read.fields);
      setMessage(read.message);
    },
  });

  const categoryItems = (facets.data?.categories ?? []).map((code) => ({
    value: code,
    label: code,
  }));
  const unitItems = (facets.data?.units ?? []).map((unit) => ({
    value: unit.code,
    label: `${unit.code} (${unit.decimals === 0 ? "whole numbers" : `${String(unit.decimals)} decimals`})`,
  }));
  const blockItems = QUOTATION_CATEGORIES.map((value) => ({
    value,
    label: QUOTATION_CATEGORY_LABELS[value],
  }));
  const readOnly = !canEdit;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>{current === null ? "New product" : current.description}</DialogTitle>
        <DialogDescription>
          {current === null
            ? "Add it to the catalogue. Prices come from the price lists; tax from its HSN code."
            : readOnly
              ? "The catalogue row, as quotations and orders read it."
              : "Change what needs it. A figure you set is the client's own from then on."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-5">
        <form
          id="product-form"
          noValidate
          aria-label={current === null ? "New product" : "Product details"}
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            setShown(true);
            setMessage(null);
            if (Object.keys(problems).length > 0 || nothing || readOnly) return;
            void submit.run();
          }}
        >
          <Field
            data-invalid={errors.description === undefined ? undefined : true}
            className="sm:col-span-2"
          >
            <FieldLabel htmlFor="product-description">Description</FieldLabel>
            <Input
              id="product-description"
              maxLength={300}
              disabled={readOnly}
              value={draft.description}
              aria-invalid={errors.description === undefined ? undefined : true}
              aria-describedby={
                errors.description === undefined
                  ? "product-description-help"
                  : "product-description-error"
              }
              onChange={(event) => {
                set({ description: event.target.value });
              }}
            />
            {errors.description === undefined ? (
              <FieldDescription id="product-description-help">
                As it prints on a quotation; no two products share one.
              </FieldDescription>
            ) : null}
            <FieldError id="product-description-error">{errors.description}</FieldError>
          </Field>

          <Field data-invalid={errors.category === undefined ? undefined : true}>
            <FieldLabel htmlFor="product-category">Category</FieldLabel>
            <Select
              items={categoryItems}
              value={draft.category}
              disabled={readOnly}
              onValueChange={(next) => {
                set({ category: typeof next === "string" ? next : null });
              }}
            >
              <SelectTrigger
                id="product-category"
                className="w-full"
                aria-invalid={errors.category === undefined ? undefined : true}
                aria-describedby={
                  errors.category === undefined ? undefined : "product-category-error"
                }
              >
                <SelectValue
                  placeholder={facets.isPending ? "Loading categories…" : "Choose a category"}
                />
              </SelectTrigger>
              <SelectContent>
                {categoryItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError id="product-category-error">{errors.category}</FieldError>
          </Field>

          <Field data-invalid={errors.uom === undefined ? undefined : true}>
            <FieldLabel htmlFor="product-uom">Unit</FieldLabel>
            <Select
              items={unitItems}
              value={draft.uom}
              disabled={readOnly}
              onValueChange={(next) => {
                set({ uom: typeof next === "string" ? next : null });
              }}
            >
              <SelectTrigger
                id="product-uom"
                className="w-full"
                aria-invalid={errors.uom === undefined ? undefined : true}
                aria-describedby={errors.uom === undefined ? undefined : "product-uom-error"}
              >
                <SelectValue placeholder={facets.isPending ? "Loading units…" : "Choose a unit"} />
              </SelectTrigger>
              <SelectContent>
                {unitItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError id="product-uom-error">{errors.uom}</FieldError>
          </Field>

          <Field>
            <FieldLabel htmlFor="product-block">Quotation block</FieldLabel>
            <Select
              items={blockItems}
              value={draft.quotationCategory}
              disabled={readOnly}
              onValueChange={(next) => {
                const chosen = QUOTATION_CATEGORIES.find((value) => value === next);
                if (chosen !== undefined) set({ quotationCategory: chosen });
              }}
            >
              <SelectTrigger
                id="product-block"
                className="w-full"
                aria-describedby="product-block-help"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {blockItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription id="product-block-help">
              Where it may sit on a subsidised quotation.
            </FieldDescription>
          </Field>

          <Field data-invalid={errors.itemCode === undefined ? undefined : true}>
            <FieldLabel htmlFor="product-code">Item code (optional)</FieldLabel>
            <Input
              id="product-code"
              autoComplete="off"
              maxLength={60}
              disabled={readOnly}
              value={draft.itemCode}
              onChange={(event) => {
                set({ itemCode: event.target.value });
              }}
            />
            <FieldError>{errors.itemCode}</FieldError>
          </Field>

          <Field data-invalid={errors.mrp === undefined ? undefined : true}>
            <FieldLabel htmlFor="product-mrp">
              MRP, ₹ (optional)
              <StandIn show={current?.provisional.includes("mrp") === true} />
            </FieldLabel>
            <Input
              id="product-mrp"
              inputMode="decimal"
              autoComplete="off"
              className="tabular-nums"
              disabled={readOnly}
              value={draft.mrp}
              aria-invalid={errors.mrp === undefined ? undefined : true}
              aria-describedby={errors.mrp === undefined ? undefined : "product-mrp-error"}
              onChange={(event) => {
                set({ mrp: event.target.value });
              }}
            />
            <FieldError id="product-mrp-error">{errors.mrp}</FieldError>
          </Field>

          <Field data-invalid={errors.packMultiple === undefined ? undefined : true}>
            <FieldLabel htmlFor="product-pack">
              Pack multiple (optional)
              <StandIn show={current?.provisional.includes("pack_multiple") === true} />
            </FieldLabel>
            <Input
              id="product-pack"
              inputMode="decimal"
              autoComplete="off"
              className="tabular-nums"
              disabled={readOnly}
              value={draft.packMultiple}
              aria-invalid={errors.packMultiple === undefined ? undefined : true}
              aria-describedby={
                errors.packMultiple === undefined ? "product-pack-help" : "product-pack-error"
              }
              onChange={(event) => {
                set({ packMultiple: event.target.value });
              }}
            />
            {errors.packMultiple === undefined ? (
              <FieldDescription id="product-pack-help">
                Quantities must be a multiple of it.
              </FieldDescription>
            ) : null}
            <FieldError id="product-pack-error">{errors.packMultiple}</FieldError>
          </Field>

          {current === null ? (
            <>
              <Field data-invalid={errors.hsn === undefined ? undefined : true}>
                <FieldLabel htmlFor="product-hsn">HSN code (optional)</FieldLabel>
                <Input
                  id="product-hsn"
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={8}
                  className="font-mono"
                  value={draft.hsn}
                  aria-invalid={errors.hsn === undefined ? undefined : true}
                  aria-describedby={
                    errors.hsn === undefined ? "product-hsn-help" : "product-hsn-error"
                  }
                  onChange={(event) => {
                    set({ hsn: event.target.value });
                  }}
                />
                {errors.hsn === undefined ? (
                  <FieldDescription id="product-hsn-help">
                    Its tax heading. Without one, quotations can&apos;t tax it.
                  </FieldDescription>
                ) : null}
                <FieldError id="product-hsn-error">{errors.hsn}</FieldError>
              </Field>
              <Field data-invalid={errors.hsnFrom === undefined ? undefined : true}>
                <FieldLabel htmlFor="product-hsn-from">From</FieldLabel>
                <Input
                  id="product-hsn-from"
                  type="date"
                  value={draft.hsnFrom}
                  aria-invalid={errors.hsnFrom === undefined ? undefined : true}
                  aria-describedby={
                    errors.hsnFrom === undefined ? undefined : "product-hsn-from-error"
                  }
                  onChange={(event) => {
                    set({ hsnFrom: event.target.value });
                  }}
                />
                <FieldError id="product-hsn-from-error">{errors.hsnFrom}</FieldError>
              </Field>
            </>
          ) : null}

          <div className="flex items-center gap-2 sm:col-span-2">
            <Checkbox
              id="product-subsidy"
              checked={draft.subsidyEligible}
              disabled={readOnly}
              onCheckedChange={(checked) => {
                set({ subsidyEligible: checked });
              }}
            />
            <Label htmlFor="product-subsidy" className="text-sm">
              Eligible for subsidy
            </Label>
          </div>
        </form>

        {message === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {message}
          </p>
        )}

        {current === null ? null : <TaxHeading product={current} canEdit={canEdit} />}
      </DialogBody>
      <DialogFooter>
        {nothing && canEdit ? (
          <p aria-live="polite" className="text-xs text-muted-foreground sm:self-center">
            Nothing changed yet.
          </p>
        ) : null}
        {current !== null && canEdit ? <ActiveToggle product={current} onDone={onClose} /> : null}
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          {readOnly ? "Close" : "Cancel"}
        </DialogClose>
        {readOnly ? null : (
          <Button
            type="submit"
            form="product-form"
            disabled={nothing}
            state={submit.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
          >
            {current === null ? "Add the product" : "Save changes"}
          </Button>
        )}
      </DialogFooter>
    </div>
  );
}

/**
 * MSTR-004 · Switch a product off (it stays on quotations already made, but no new line can
 * carry it) or back on. Nothing is ever deleted.
 */
function ActiveToggle({
  product,
  onDone,
}: {
  product: Product;
  onDone: () => void;
}): React.JSX.Element {
  const patch = usePatchProduct();
  const idempotency = useIdempotencyKey();
  const toggle = useAsyncAction({
    action: () => {
      const body = { is_active: !product.active };
      return patch.mutateAsync({
        productId: product.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: product.id, ...body }),
      });
    },
    logger: log,
    fn: "handleToggleProduct",
    dataId: "MSTR-004",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(saved.active ? "Product switched on" : "Product switched off", {
        description: saved.active
          ? saved.description
          : "New quotations and orders can't add it; ones already made keep it.",
      });
      onDone();
    },
    onError: (error) => {
      toast.error(readRefusal(error).message ?? "Not saved");
    },
  });
  return (
    <Button
      type="button"
      variant="ghost"
      className="sm:mr-auto"
      state={toggle.state}
      loadingLabel="Saving…"
      successLabel="Saved"
      errorLabel="Not saved"
      onClick={() => {
        void toggle.run();
      }}
    >
      {product.active ? "Switch off" : "Switch on"}
    </Button>
  );
}

/**
 * MSTR-005 · A product's tariff heading: the one in force with its slab, the history, and a new
 * heading from a date. The slab follows the heading (the Tax rates tab sets it per code).
 */
function TaxHeading({
  product,
  canEdit,
}: {
  product: Product;
  canEdit: boolean;
}): React.JSX.Element {
  const history = useQuery(hsnHistoryQueryOptions(product.id));
  const assign = useAssignHsn();
  const idempotency = useIdempotencyKey();
  const [code, setCode] = useState("");
  const [from, setFrom] = useState(todayInIndia);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const codeProblem = /^\d{4,8}$/.test(code.trim()) ? null : "Four to eight digits.";
  const fromProblem = /^\d{4}-\d{2}-\d{2}$/.test(from) ? null : "Choose the day it starts.";

  const submit = useAsyncAction({
    action: () => {
      const request = { productId: product.id, hsnCode: code.trim(), from };
      return assign.mutateAsync({ ...request, idempotencyKey: idempotency.keyFor(request) });
    },
    logger: log,
    fn: "handleAssignHsn",
    dataId: "MSTR-005",
    onSuccess: () => {
      idempotency.reset();
      setCode("");
      setShown(false);
      toast.success(`HSN ${code.trim()} from ${dayText(from)}`);
    },
    onError: (error) => {
      const read = readRefusal(error, { hsn_code: "code", effective_from: "from" });
      setRefusal(read.message ?? Object.values(read.fields).join(" "));
    },
  });

  return (
    <section
      aria-labelledby="tax-heading-title"
      className="flex flex-col gap-3 border-t border-border pt-4"
    >
      <div className="flex flex-col gap-0.5">
        <h3 id="tax-heading-title" className="text-sm font-semibold text-foreground">
          Tax
        </h3>
        <p className="text-sm text-muted-foreground">
          {product.hsnCode === null ? (
            "No HSN code yet: quotations can't tax it until it has one."
          ) : (
            <>
              HSN {product.hsnCode}
              <StandIn show={product.provisional.includes("hsn_code")} /> ·{" "}
              {product.gstSlab === null
                ? "no GST slab for this code yet"
                : `GST ${slabText(product.gstSlab)}`}
              <StandIn show={product.provisional.includes("gst_slab")} />
            </>
          )}
        </p>
      </div>
      {history.data === undefined || history.data.length < 2 ? null : (
        <ol aria-label="HSN history" className="flex flex-col gap-1 text-xs text-muted-foreground">
          {history.data.map((row) => (
            <li key={row.id}>
              {row.hsnCode} ·{" "}
              {row.to === null
                ? `from ${dayText(row.from)}`
                : `${dayText(row.from)} until ${dayText(row.to)}`}
            </li>
          ))}
        </ol>
      )}
      {canEdit ? (
        <form
          noValidate
          aria-label="Change the HSN code"
          className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-start"
          onSubmit={(event) => {
            event.preventDefault();
            setShown(true);
            setRefusal(null);
            if (codeProblem !== null || fromProblem !== null) return;
            void submit.run();
          }}
        >
          <Field data-invalid={shown && codeProblem !== null ? true : undefined}>
            <FieldLabel htmlFor="hsn-code">
              {product.hsnCode === null ? "HSN code" : "New HSN code"}
            </FieldLabel>
            <Input
              id="hsn-code"
              inputMode="numeric"
              autoComplete="off"
              maxLength={8}
              className="font-mono"
              value={code}
              aria-invalid={shown && codeProblem !== null ? true : undefined}
              aria-describedby={shown && codeProblem !== null ? "hsn-code-error" : undefined}
              onChange={(event) => {
                setCode(event.target.value);
              }}
            />
            <FieldError id="hsn-code-error">{shown ? codeProblem : null}</FieldError>
          </Field>
          <Field data-invalid={shown && fromProblem !== null ? true : undefined}>
            <FieldLabel htmlFor="hsn-from">From</FieldLabel>
            <Input
              id="hsn-from"
              type="date"
              value={from}
              onChange={(event) => {
                setFrom(event.target.value);
              }}
            />
            <FieldError>{shown ? fromProblem : null}</FieldError>
          </Field>
          <Button
            type="submit"
            variant="outline"
            className="sm:mt-6"
            state={submit.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
          >
            {product.hsnCode === null ? "Set HSN" : "Change HSN"}
          </Button>
          {refusal === null ? null : (
            <p role="alert" className="text-sm text-danger sm:col-span-3">
              {refusal}
            </p>
          )}
        </form>
      ) : null}
      {product.provisional.length === 0 ? null : (
        <p className="text-xs text-muted-foreground">
          Stand-ins until the client confirms them:{" "}
          {product.provisional.map((field) => PROVISIONAL_LABELS[field]).join(", ")}.
        </p>
      )}
    </section>
  );
}
