"use client";

import { Add01Icon, ShoppingBasket01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCreateMaterial, usePatchMaterial } from "@/features/marketing/api/marketing.mutations";
import { materialsQueryOptions } from "@/features/marketing/api/marketing.queries";
import type { Material } from "@/features/marketing/api/marketing.schemas";
import { percentText } from "@/features/marketing/lib/marketing-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/marketing/components/catalogue-admin.tsx",
  dataId: "MKT-002",
});

type Opened = { readonly kind: "add" } | { readonly kind: "edit"; readonly material: Material };

/**
 * MKT-002 · The catalogue for the marketing team (marketing_material.edit): every item with
 * today's price and the company's share. Add an item, change one (a new price starts today and
 * can be corrected the same day until an order uses it), or switch one off; orders already
 * placed keep their own figures.
 */
export function CatalogueAdmin(): React.JSX.Element {
  const query = useQuery(materialsQueryOptions(false));
  const [opened, setOpened] = useState<Opened | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          A new price starts today. Orders already placed keep their own prices.
        </p>
        <Button
          onClick={() => {
            setOpened({ kind: "add" });
          }}
        >
          <Icon icon={Add01Icon} />
          Add an item
        </Button>
      </div>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading the catalogue" className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((row) => (
            <Skeleton key={row} className="h-14 w-full rounded-lg" />
          ))}
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
          icon={ShoppingBasket01Icon}
          title="The catalogue is empty"
          description="Add the first item, with its price and the company's share."
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <ul
          aria-label="Catalogue items"
          className="flex flex-col divide-y divide-border rounded-xl border border-border bg-card"
        >
          {query.data.map((material) => (
            <CatalogueRow
              key={material.id}
              material={material}
              onEdit={() => {
                setOpened({ kind: "edit", material });
              }}
            />
          ))}
        </ul>
      )}

      <Dialog
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null);
        }}
      >
        <DialogContent>
          {opened === null ? null : (
            <MaterialForm
              material={opened.kind === "edit" ? opened.material : null}
              onClose={() => {
                setOpened(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CatalogueRow({
  material,
  onEdit,
}: {
  material: Material;
  onEdit: () => void;
}): React.JSX.Element {
  const patch = usePatchMaterial();
  const idempotency = useIdempotencyKey();
  const toggle = useAsyncAction({
    action: () => {
      const body = { is_active: !material.active };
      return patch.mutateAsync({
        materialId: material.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: material.id, ...body }),
      });
    },
    logger: log,
    fn: "handleToggleMaterial",
    dataId: "MKT-002",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(saved.active ? `${saved.name} is offered again` : `${saved.name} switched off`);
    },
    onError: (error) => {
      toast.error(toUserFacingError(error).title);
    },
  });

  return (
    <li
      className={cn(
        "flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4",
        !material.active && "bg-muted",
      )}
    >
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
          {material.name}
          {material.active ? null : (
            <Badge variant="neutral" size="sm">
              Switched off
            </Badge>
          )}
          {material.provisional ? (
            <Badge variant="outline" size="sm">
              Indicative price
            </Badge>
          ) : null}
        </span>
        <span className="text-xs text-muted-foreground tabular-nums">
          <span className="font-mono">{material.code}</span> ·{" "}
          {material.price === null
            ? "No price in force"
            : `${formatInr(material.price, { paise: true })} / ${material.unit}`}{" "}
          · company pays {percentText(material.companySharePct)}
        </span>
      </span>
      <span className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" aria-label={`Change ${material.name}`} onClick={onEdit}>
          Change
        </Button>
        <Button
          size="sm"
          variant="ghost"
          aria-label={
            material.active ? `Switch off ${material.name}` : `Offer ${material.name} again`
          }
          state={toggle.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
          onClick={() => {
            void toggle.run();
          }}
        >
          {material.active ? "Switch off" : "Offer again"}
        </Button>
      </span>
    </li>
  );
}

interface Draft {
  readonly code: string;
  readonly name: string;
  readonly unit: string;
  readonly price: string;
  readonly share: string;
  readonly description: string;
}

type FieldName = "code" | "name" | "unit" | "price" | "share" | "description";

/** The backend's field names onto the form's. */
const WIRE_FIELDS: Readonly<Record<string, FieldName>> = {
  code: "code",
  name: "name",
  unit: "unit",
  price: "price",
  company_share_pct: "share",
  description: "description",
};

function problemsOf(draft: Draft, adding: boolean): Partial<Record<FieldName, string>> {
  const problems: Partial<Record<FieldName, string>> = {};
  if (adding && draft.code.trim() === "") problems.code = "Give it a code, like MM-CAP.";
  if (draft.name.trim() === "") problems.name = "Name it.";
  if (draft.unit.trim() === "") problems.unit = "Say how it is counted, like Nos.";
  if (!/^\d+(\.\d{1,2})?$/.test(draft.price.trim())) problems.price = "Rupees, like 120 or 120.50.";
  const share = draft.share.trim();
  if (!/^\d+(\.\d{1,3})?$/.test(share) || Number(share) > 100) {
    problems.share = "A percentage from 0 to 100.";
  }
  return problems;
}

function MaterialForm({
  material,
  onClose,
}: {
  material: Material | null;
  onClose: () => void;
}): React.JSX.Element {
  const adding = material === null;
  const create = useCreateMaterial();
  const patch = usePatchMaterial();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [draft, setDraft] = useState<Draft>({
    code: "",
    name: material?.name ?? "",
    unit: material?.unit ?? "Nos",
    price: material?.price ?? "",
    share:
      material?.companySharePct === null || material === null
        ? "50"
        : String(Number(material.companySharePct)),
    description: material?.description ?? "",
  });
  const [shown, setShown] = useState(false);
  const [serverProblems, setServerProblems] = useState<Partial<Record<FieldName, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems = { ...(shown ? problemsOf(draft, adding) : {}), ...serverProblems };

  const set = (patchDraft: Partial<Draft>): void => {
    setDraft({ ...draft, ...patchDraft });
    setServerProblems({});
  };

  const submit = useAsyncAction({
    action: () => {
      const common = {
        name: draft.name.trim(),
        unit: draft.unit.trim(),
        price: draft.price.trim(),
        company_share_pct: draft.share.trim(),
        description: draft.description.trim() === "" ? null : draft.description.trim(),
      };
      if (material === null) {
        const body = { ...common, code: draft.code.trim() };
        return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
      }
      return patch.mutateAsync({
        materialId: material.id,
        body: common,
        idempotencyKey: idempotency.keyFor({ id: material.id, ...common }),
      });
    },
    logger: log,
    fn: adding ? "handleCreateMaterial" : "handlePatchMaterial",
    dataId: "MKT-002",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(adding ? `${saved.name} added` : `${saved.name} saved`);
      closeSoon();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "code_taken") {
        setServerProblems({ code: "That code is taken." });
        return;
      }
      if (isApiError(error) && error.code === "price_changed_today") {
        setServerProblems({
          price: "The price was changed today and an order has used it. Change it tomorrow.",
        });
        return;
      }
      const fields = readFieldErrors(error);
      const mapped: Partial<Record<FieldName, string>> = {};
      for (const [key, reason] of Object.entries(fields ?? {})) {
        const name = WIRE_FIELDS[key];
        if (name !== undefined) mapped[name] = reason;
      }
      if (Object.keys(mapped).length > 0) {
        setServerProblems(mapped);
        return;
      }
      setRefusal(toUserFacingError(error).title);
    },
  });

  const field = (
    name: FieldName,
    label: string,
    control: (props: {
      id: string;
      "aria-invalid": true | undefined;
      "aria-describedby": string | undefined;
    }) => React.ReactNode,
    help?: string,
  ): React.JSX.Element => {
    const id = `material-${name}`;
    const problem = problems[name];
    const describedBy = [
      problem === undefined ? null : `${id}-error`,
      help === undefined ? null : `${id}-help`,
    ]
      .filter((value) => value !== null)
      .join(" ");
    return (
      <Field data-invalid={problem === undefined ? undefined : true}>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        {control({
          id,
          "aria-invalid": problem === undefined ? undefined : true,
          "aria-describedby": describedBy === "" ? undefined : describedBy,
        })}
        {help === undefined ? null : <FieldDescription id={`${id}-help`}>{help}</FieldDescription>}
        {problem === undefined ? null : <FieldError id={`${id}-error`}>{problem}</FieldError>}
      </Field>
    );
  };

  return (
    <form
      noValidate
      aria-label={adding ? "Add a catalogue item" : `Change ${material.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (Object.keys(problemsOf(draft, adding)).length > 0) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>{adding ? "Add a catalogue item" : `Change ${material.name}`}</DialogTitle>
        <DialogDescription>
          {adding
            ? "It is offered from today, at this price."
            : `${material.code}. A new price or share starts today.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="grid gap-4 sm:grid-cols-2">
        {adding
          ? field("code", "Code", (props) => (
              <Input
                {...props}
                autoComplete="off"
                maxLength={40}
                placeholder="MM-CAP"
                value={draft.code}
                onChange={(event) => {
                  set({ code: event.target.value.toUpperCase() });
                }}
              />
            ))
          : null}
        {field("name", "Name", (props) => (
          <Input
            {...props}
            maxLength={120}
            value={draft.name}
            onChange={(event) => {
              set({ name: event.target.value });
            }}
          />
        ))}
        {field("unit", "Unit", (props) => (
          <Input
            {...props}
            maxLength={20}
            value={draft.unit}
            onChange={(event) => {
              set({ unit: event.target.value });
            }}
          />
        ))}
        {field("price", "Price", (props) => (
          <InputGroup>
            <InputGroupAddon>₹</InputGroupAddon>
            <InputGroupInput
              {...props}
              inputMode="decimal"
              autoComplete="off"
              className="tabular-nums"
              value={draft.price}
              onChange={(event) => {
                set({ price: event.target.value });
              }}
            />
          </InputGroup>
        ))}
        {field(
          "share",
          "Company pays",
          (props) => (
            <InputGroup>
              <InputGroupInput
                {...props}
                inputMode="decimal"
                autoComplete="off"
                className="tabular-nums"
                value={draft.share}
                onChange={(event) => {
                  set({ share: event.target.value });
                }}
              />
              <InputGroupAddon align="end">%</InputGroupAddon>
            </InputGroup>
          ),
          "The dealer pays the rest. An office's own use is all the company's.",
        )}
        <div className="sm:col-span-2">
          {field("description", "Description (optional)", (props) => (
            <Textarea
              {...props}
              rows={2}
              maxLength={300}
              value={draft.description}
              onChange={(event) => {
                set({ description: event.target.value });
              }}
            />
          ))}
        </div>
        {refusal === null ? null : (
          <p
            role="alert"
            className="rounded-md bg-danger-soft p-3 text-sm text-danger sm:col-span-2"
          >
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
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {adding ? "Add item" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
