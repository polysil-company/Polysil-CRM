"use client";

import { Add01Icon, Store01Icon } from "@hugeicons/core-free-icons";
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
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateWarehouse, usePatchWarehouse } from "@/features/stock/api/stock.mutations";
import { warehousesQueryOptions } from "@/features/stock/api/stock.queries";
import type { Warehouse } from "@/features/stock/api/stock.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/stock/components/warehouses-admin.tsx",
  dataId: "MSTR-016",
});

/**
 * MSTR-016 · The depots and warehouses (stock.edit): add one, rename it, make it the default
 * (an order without a choice is served from it), or switch it off. The default can't be switched
 * off until another one is the default.
 */
export function WarehousesAdmin(): React.JSX.Element {
  const query = useQuery(warehousesQueryOptions(true));
  const [editing, setEditing] = useState<Warehouse | "new" | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          An order without a choice is served from the default warehouse.
        </p>
        <Button
          onClick={() => {
            setEditing("new");
          }}
        >
          <Icon icon={Add01Icon} />
          Add a warehouse
        </Button>
      </div>
      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading warehouses" className="flex flex-col gap-2">
          {[0, 1, 2].map((row) => (
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
          icon={Store01Icon}
          title="No warehouses yet"
          description="Add the first depot; it becomes the default."
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <ul
          aria-label="Warehouses"
          className="flex flex-col divide-y divide-border rounded-xl border border-border bg-card"
        >
          {query.data.map((warehouse) => (
            <WarehouseRow
              key={warehouse.id}
              warehouse={warehouse}
              onEdit={() => {
                setEditing(warehouse);
              }}
            />
          ))}
        </ul>
      )}
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent size="sm">
          {editing === null ? null : (
            <WarehouseForm
              warehouse={editing === "new" ? null : editing}
              first={query.data?.length === 0}
              onClose={() => {
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function WarehouseRow({
  warehouse,
  onEdit,
}: {
  warehouse: Warehouse;
  onEdit: () => void;
}): React.JSX.Element {
  const patch = usePatchWarehouse();
  const idempotency = useIdempotencyKey();
  const change = (
    body: { is_default?: boolean; is_active?: boolean },
    done: string,
  ): Promise<Warehouse> =>
    patch
      .mutateAsync({
        warehouseId: warehouse.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: warehouse.id, ...body }),
      })
      .then((saved) => {
        idempotency.reset();
        toast.success(done);
        return saved;
      });
  const onError = (error: unknown): void => {
    toast.error(
      isApiError(error) && error.code === "default_warehouse"
        ? "Make another warehouse the default first."
        : toUserFacingError(error).title,
    );
  };
  const makeDefault = useAsyncAction({
    action: () => change({ is_default: true }, `${warehouse.name} is now the default`),
    logger: log,
    fn: "handleMakeDefault",
    dataId: "MSTR-016",
    onError,
  });
  const toggle = useAsyncAction({
    action: () =>
      change(
        { is_active: !warehouse.active },
        warehouse.active ? `${warehouse.name} switched off` : `${warehouse.name} switched on`,
      ),
    logger: log,
    fn: "handleToggleWarehouse",
    dataId: "MSTR-016",
    onError,
  });

  return (
    <li
      className={cn(
        "flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4",
        !warehouse.active && "bg-muted",
      )}
    >
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
          {warehouse.name}
          {warehouse.isDefault ? (
            <Badge variant="info" size="sm">
              Default
            </Badge>
          ) : null}
          {warehouse.active ? null : (
            <Badge variant="neutral" size="sm">
              Switched off
            </Badge>
          )}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{warehouse.code}</span>
      </span>
      <span className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          aria-label={`Change ${warehouse.name}`}
          onClick={onEdit}
        >
          Change
        </Button>
        {warehouse.isDefault || !warehouse.active ? null : (
          <Button
            size="sm"
            variant="outline"
            aria-label={`Make ${warehouse.name} the default`}
            state={makeDefault.state}
            loadingLabel="Saving…"
            successLabel="Default"
            errorLabel="Not saved"
            onClick={() => {
              void makeDefault.run();
            }}
          >
            Make default
          </Button>
        )}
        {warehouse.isDefault ? null : (
          <Button
            size="sm"
            variant="ghost"
            aria-label={
              warehouse.active ? `Switch off ${warehouse.name}` : `Switch on ${warehouse.name}`
            }
            state={toggle.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
            onClick={() => {
              void toggle.run();
            }}
          >
            {warehouse.active ? "Switch off" : "Switch on"}
          </Button>
        )}
      </span>
    </li>
  );
}

function WarehouseForm({
  warehouse,
  first,
  onClose,
}: {
  warehouse: Warehouse | null;
  first: boolean;
  onClose: () => void;
}): React.JSX.Element {
  const create = useCreateWarehouse();
  const patch = usePatchWarehouse();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [code, setCode] = useState(warehouse?.code ?? "");
  const [name, setName] = useState(warehouse?.name ?? "");
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<{ code?: string | undefined; name?: string | undefined }>(
    {},
  );
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems = {
    code:
      server.code ??
      (shown && code.trim() === "" ? "Give it a short code, like AHD-1." : undefined),
    name:
      server.name ?? (shown && name.trim() === "" ? "Name it, like Ahmedabad depot." : undefined),
  };

  const submit = useAsyncAction({
    action: () => {
      if (warehouse === null) {
        const body = {
          code: code.trim(),
          name: name.trim(),
          territory_id: null,
          // The first warehouse is the default: an order must be served from somewhere.
          is_default: first,
          is_active: true,
        };
        return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
      }
      const body = { code: code.trim(), name: name.trim() };
      return patch.mutateAsync({
        warehouseId: warehouse.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: warehouse.id, ...body }),
      });
    },
    logger: log,
    fn: warehouse === null ? "handleCreateWarehouse" : "handlePatchWarehouse",
    dataId: "MSTR-016",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(warehouse === null ? `${saved.name} added` : `${saved.name} saved`);
      closeSoon();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "code_taken") {
        setServer({ code: "Another warehouse has this code." });
        return;
      }
      const fields = readFieldErrors(error) ?? {};
      if (fields.code !== undefined || fields.name !== undefined) {
        setServer({ code: fields.code, name: fields.name });
        return;
      }
      setRefusal(toUserFacingError(error).title);
    },
  });

  return (
    <form
      noValidate
      aria-label={warehouse === null ? "Add a warehouse" : `Change ${warehouse.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (code.trim() === "" || name.trim() === "") return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {warehouse === null ? "Add a warehouse" : `Change ${warehouse.name}`}
        </DialogTitle>
        <DialogDescription>
          {warehouse === null && first
            ? "The first warehouse is the default."
            : "Codes are unique, ignoring case."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={problems.code === undefined ? undefined : true}>
          <FieldLabel htmlFor="warehouse-code">Code</FieldLabel>
          <Input
            id="warehouse-code"
            autoComplete="off"
            maxLength={20}
            value={code}
            aria-invalid={problems.code === undefined ? undefined : true}
            aria-describedby={problems.code === undefined ? undefined : "warehouse-code-error"}
            onChange={(event) => {
              setCode(event.target.value.toUpperCase());
              setServer({});
            }}
          />
          {problems.code === undefined ? null : (
            <FieldError id="warehouse-code-error">{problems.code}</FieldError>
          )}
        </Field>
        <Field data-invalid={problems.name === undefined ? undefined : true}>
          <FieldLabel htmlFor="warehouse-name">Name</FieldLabel>
          <Input
            id="warehouse-name"
            autoComplete="off"
            maxLength={120}
            value={name}
            aria-invalid={problems.name === undefined ? undefined : true}
            aria-describedby={problems.name === undefined ? undefined : "warehouse-name-error"}
            onChange={(event) => {
              setName(event.target.value);
              setServer({});
            }}
          />
          {problems.name === undefined ? null : (
            <FieldError id="warehouse-name-error">{problems.name}</FieldError>
          )}
        </Field>
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
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {warehouse === null ? "Add warehouse" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
