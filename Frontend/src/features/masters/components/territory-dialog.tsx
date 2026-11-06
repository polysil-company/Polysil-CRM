"use client";

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
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useCreateTerritory, usePatchTerritory } from "@/features/masters/api/masters.mutations";
import {
  TERRITORY_LEVELS,
  type Territory,
  type TerritoryLevel,
  type TerritoryPatchRequest,
} from "@/features/masters/api/masters.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/masters/components/territory-dialog.tsx",
  dataId: "MSTR-012",
});

const LEVEL_LABELS: Readonly<Record<TerritoryLevel, string>> = {
  state: "State",
  district: "District",
  taluka: "Taluka",
  village: "Village",
};

type TerritoryField = "name" | "code" | "parent_id";

/** The level one up, or null for a state. */
function parentLevel(level: TerritoryLevel): TerritoryLevel | null {
  const index = TERRITORY_LEVELS.indexOf(level);
  return index <= 0 ? null : (TERRITORY_LEVELS[index - 1] ?? null);
}

/**
 * MSTR-012 · A new territory (a state, or one level down under its parent) or a change to
 * one: its name and code. A state's code is locked once a lead is numbered with it.
 */
export function TerritoryForm({
  territory,
  onDone,
}: {
  /** Null: a new one. */
  territory: Territory | null;
  onDone: () => void;
}): React.JSX.Element {
  const create = useCreateTerritory();
  const patch = usePatchTerritory();
  const [level, setLevel] = useState<TerritoryLevel>(territory?.level ?? "district");
  const [parent, setParent] = useState<TerritoryChoice | null>(null);
  const [name, setName] = useState(territory?.name ?? "");
  const [code, setCode] = useState(territory?.code ?? "");
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<Partial<Record<TerritoryField, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const above = parentLevel(level);
  const locked = territory?.codeLocked ?? false;

  const local: Partial<Record<TerritoryField, string>> = {};
  if (name.trim() === "") local.name = "Enter the name.";
  if (territory === null && above !== null && parent === null) {
    local.parent_id = `Choose the ${LEVEL_LABELS[above].toLowerCase()} it sits in.`;
  }
  if (code.trim() !== "" && !/^[A-Za-z0-9-]{1,10}$/.test(code.trim())) {
    local.code = "Letters, digits or a hyphen, up to 10.";
  }
  const problems = { ...(shown ? local : {}), ...server };

  const changes: TerritoryPatchRequest =
    territory === null
      ? {}
      : {
          ...(name.trim() === territory.name ? {} : { name: name.trim() }),
          ...(code.trim().toUpperCase() === (territory.code ?? "")
            ? {}
            : { code: code.trim() === "" ? null : code.trim().toUpperCase() }),
        };

  const save = useAsyncAction({
    action: () =>
      territory === null
        ? create.mutateAsync({
            name: name.trim(),
            level,
            parent_id: above === null ? null : (parent?.id ?? null),
            code: code.trim() === "" ? null : code.trim().toUpperCase(),
          })
        : patch.mutateAsync({ territoryId: territory.id, body: changes }),
    logger: log,
    fn: territory === null ? "handleCreateTerritory" : "handlePatchTerritory",
    dataId: "MSTR-012",
    onSuccess: (saved) => {
      toast.success(territory === null ? `${saved.name} added` : `${saved.name} saved`);
      onDone();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null) {
        const mapped: Partial<Record<TerritoryField, string>> = {};
        if (fields.name !== undefined) mapped.name = "Another territory here has this name.";
        if (fields.code !== undefined) {
          mapped.code = fields.code.includes("can't change")
            ? "Leads are numbered with this code: it can't change."
            : "Another territory at this level has this code.";
        }
        if (fields.parent_id !== undefined) mapped.parent_id = fields.parent_id;
        setServer(mapped);
        if (Object.keys(mapped).length > 0) return;
      }
      setRefusal(toUserFacingError(error).description);
    },
  });

  return (
    <form
      noValidate
      aria-label={territory === null ? "New territory" : `Edit ${territory.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer({});
        setRefusal(null);
        if (Object.keys(local).length > 0) return;
        if (territory !== null && Object.keys(changes).length === 0) {
          onDone();
          return;
        }
        void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>{territory === null ? "New territory" : `Edit ${territory.name}`}</DialogTitle>
        <DialogDescription>
          {territory === null
            ? "A state, or a district, taluka or village in the level above."
            : `${LEVEL_LABELS[territory.level]}${territory.parent === null ? "" : ` in ${territory.parent.name}`}.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {territory === null ? (
          <Field>
            <FieldLabel id="territory-level-label">Level</FieldLabel>
            <RadioGroup<TerritoryLevel>
              aria-labelledby="territory-level-label"
              value={level}
              onValueChange={(next) => {
                setLevel(next);
                setParent(null);
              }}
              className="flex-row flex-wrap gap-5"
            >
              {TERRITORY_LEVELS.map((item) => (
                <label key={item} className="flex items-center gap-2 text-sm text-foreground">
                  <RadioGroupItem value={item} />
                  {LEVEL_LABELS[item]}
                </label>
              ))}
            </RadioGroup>
          </Field>
        ) : null}
        {territory === null && above !== null ? (
          <Field data-invalid={problems.parent_id === undefined ? undefined : true}>
            <FieldLabel htmlFor="territory-parent">
              In which {LEVEL_LABELS[above].toLowerCase()}
            </FieldLabel>
            <TerritoryPicker
              id="territory-parent"
              value={parent}
              onValueChange={setParent}
              levels={[above]}
              placeholder={`Search a ${LEVEL_LABELS[above].toLowerCase()}`}
              aria-invalid={problems.parent_id === undefined ? undefined : true}
              aria-describedby={
                problems.parent_id === undefined ? undefined : "territory-parent-error"
              }
            />
            <FieldError id="territory-parent-error">{problems.parent_id}</FieldError>
          </Field>
        ) : null}
        <Field data-invalid={problems.name === undefined ? undefined : true}>
          <FieldLabel htmlFor="territory-name">Name</FieldLabel>
          <Input
            id="territory-name"
            value={name}
            maxLength={120}
            autoComplete="off"
            aria-invalid={problems.name === undefined ? undefined : true}
            aria-describedby={problems.name === undefined ? undefined : "territory-name-error"}
            onChange={(event) => {
              setName(event.target.value);
              setServer({});
            }}
          />
          <FieldError id="territory-name-error">{problems.name}</FieldError>
        </Field>
        <Field data-invalid={problems.code === undefined ? undefined : true}>
          <FieldLabel htmlFor="territory-code">
            Code
            {level === "state" ? null : (
              <span className="font-normal text-muted-foreground">(optional)</span>
            )}
          </FieldLabel>
          <Input
            id="territory-code"
            value={code}
            maxLength={10}
            autoComplete="off"
            className="font-mono uppercase"
            disabled={locked}
            aria-invalid={problems.code === undefined ? undefined : true}
            aria-describedby={
              problems.code === undefined ? "territory-code-hint" : "territory-code-error"
            }
            onChange={(event) => {
              setCode(event.target.value);
              setServer({});
            }}
          />
          {problems.code === undefined ? (
            <FieldDescription id="territory-code-hint">
              {locked
                ? "Leads are numbered with this code, so it can't change."
                : level === "state"
                  ? "Two letters, like GJ: leads here are numbered POL/GJ/…. It can't change once a lead is numbered."
                  : "Unique at this level."}
            </FieldDescription>
          ) : null}
          <FieldError id="territory-code-error">{problems.code}</FieldError>
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {territory === null ? "Add territory" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
