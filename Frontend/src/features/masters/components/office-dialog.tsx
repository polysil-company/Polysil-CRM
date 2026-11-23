"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

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
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useCreateOffice, usePatchOffice } from "@/features/masters/api/masters.mutations";
import type {
  Office,
  OfficeCreateRequest,
  OfficePatchRequest,
} from "@/features/masters/api/masters.schemas";
import { roleListQueryOptions } from "@/features/users/api/users.queries";
import { OfficePicker, type OfficeValue } from "@/features/users/components/office-picker";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/masters/components/office-dialog.tsx",
  dataId: "MSTR-011",
});

export const OFFICE_NAME_MAX_LENGTH = 120;

/** What the form holds, as typed. */
export interface OfficeDraft {
  readonly name: string;
  readonly level: string | null;
  /** Null with `root`: an office at the top of the tree. */
  readonly parent: OfficeValue | null;
  readonly root: boolean;
  /** Null with `hq`: an HQ unit covers no territory. */
  readonly territory: TerritoryChoice | null;
  readonly hq: boolean;
}

export function emptyOfficeDraft(): OfficeDraft {
  return { name: "", level: null, parent: null, root: false, territory: null, hq: false };
}

export function draftOfOffice(office: Office): OfficeDraft {
  return {
    name: office.name,
    level: String(office.roleLevel),
    parent: office.parent,
    root: office.parent === null,
    territory: office.territory,
    hq: office.territory === null,
  };
}

type OfficeField = "name" | "level" | "parent" | "territory";

/** What is missing before the office can be saved. */
export function officeProblems(
  mode: "create" | "edit",
  draft: OfficeDraft,
): Partial<Record<OfficeField, string>> {
  return {
    ...(draft.name.trim() === "" ? { name: "Enter the office's name." } : {}),
    ...(mode === "create" && draft.level === null ? { level: "Choose the level." } : {}),
    ...(!draft.root && draft.parent === null
      ? { parent: "Choose the office it sits under, or make it a top-level office." }
      : {}),
    ...(!draft.hq && draft.territory === null
      ? { territory: "Choose the territory it covers, or mark it an HQ unit." }
      : {}),
  };
}

export function createRequestOfOffice(draft: OfficeDraft): OfficeCreateRequest {
  return {
    name: draft.name.trim(),
    role_level: Number(draft.level),
    parent_id: draft.root ? null : (draft.parent?.id ?? null),
    territory_id: draft.hq ? null : (draft.territory?.id ?? null),
  };
}

/** Only what changed, as PATCH takes it. */
export function patchRequestOfOffice(office: Office, draft: OfficeDraft): OfficePatchRequest {
  const parentId = draft.root ? null : (draft.parent?.id ?? null);
  const territoryId = draft.hq ? null : (draft.territory?.id ?? null);
  return {
    ...(draft.name.trim() === office.name ? {} : { name: draft.name.trim() }),
    ...(parentId === (office.parent?.id ?? null) ? {} : { parent_id: parentId }),
    ...(territoryId === (office.territory?.id ?? null) ? {} : { territory_id: territoryId }),
  };
}

const WIRE_FIELDS: Readonly<Record<string, OfficeField>> = {
  name: "name",
  role_level: "level",
  parent_id: "parent",
  territory_id: "territory",
};

/**
 * MSTR-011 · Add an office, or rename, move and re-cover one. The level is set when it is
 * added; the levels come from the roles, so the choice reads "2 · District Manager". The
 * backend refuses a name already used beside it, a closed parent, and a move under one of
 * its own offices, each on its field.
 */
export function OfficeForm({
  office,
  onDone,
}: {
  /** Null to add one. */
  office: Office | null;
  onDone: () => void;
}): React.JSX.Element {
  const mode = office === null ? "create" : "edit";
  const [draft, setDraft] = useState<OfficeDraft>(
    office === null ? emptyOfficeDraft() : draftOfOffice(office),
  );
  const [problems, setProblems] = useState<Partial<Record<OfficeField, string>>>({});
  const roles = useQuery(roleListQueryOptions());
  const create = useCreateOffice();
  const patch = usePatchOffice();
  const levels = [
    ...new Map(
      (roles.data ?? [])
        .filter((role) => !role.portal)
        .toSorted((a, b) => a.level - b.level)
        .map((role) => [role.level, role.name]),
    ),
  ].map(([level, name]) => ({ value: String(level), label: `${String(level)} · ${name}` }));
  const changes = office === null ? null : patchRequestOfOffice(office, draft);
  const nothingChanged = changes !== null && Object.keys(changes).length === 0;

  const save = useAsyncAction({
    action: () =>
      office === null
        ? create.mutateAsync(createRequestOfOffice(draft))
        : patch.mutateAsync({ officeId: office.id, body: changes ?? {} }),
    logger: log,
    fn: office === null ? "handleCreateOffice" : "handlePatchOffice",
    dataId: "MSTR-011",
    onSuccess: (saved) => {
      toast.success(office === null ? `${saved.name} added` : `${saved.name} saved`);
      onDone();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      const mapped: Partial<Record<OfficeField, string>> = {};
      for (const [wire, message] of Object.entries(fields)) {
        const field = WIRE_FIELDS[wire];
        if (field !== undefined) mapped[field] = message;
      }
      if (Object.keys(mapped).length > 0) {
        setProblems(mapped);
        return;
      }
      toast.error(office === null ? "Office not added" : "Office not saved", {
        description: toUserFacingError(error).description,
      });
    },
  });

  const set = (next: Partial<OfficeDraft>): void => {
    setDraft((before) => ({ ...before, ...next }));
  };
  const invalid = (field: OfficeField): true | undefined =>
    problems[field] === undefined ? undefined : true;

  return (
    <form
      noValidate
      aria-label={office === null ? "New office" : `Edit ${office.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        const found = officeProblems(mode, draft);
        setProblems(found);
        if (Object.keys(found).length === 0) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>{office === null ? "New office" : `Edit ${office.name}`}</DialogTitle>
        <DialogDescription>
          {office === null
            ? "Where it sits in the office tree, and the territory its people cover."
            : "A move or a new territory changes what its people see at once."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={invalid("name")}>
          <FieldLabel htmlFor="office-name">Name</FieldLabel>
          <Input
            id="office-name"
            value={draft.name}
            maxLength={OFFICE_NAME_MAX_LENGTH}
            autoComplete="off"
            aria-invalid={invalid("name")}
            aria-describedby={invalid("name") ? "office-name-error" : "office-name-hint"}
            onChange={(event) => {
              set({ name: event.target.value });
            }}
          />
          {problems.name === undefined ? (
            <FieldDescription id="office-name-hint">
              Unique among the offices beside it.
            </FieldDescription>
          ) : null}
          <FieldError id="office-name-error">{problems.name}</FieldError>
        </Field>

        {office === null ? (
          <Field data-invalid={invalid("level")}>
            <FieldLabel htmlFor="office-level">Level</FieldLabel>
            <Select
              items={levels}
              value={draft.level}
              onValueChange={(next) => {
                set({ level: typeof next === "string" ? next : null });
              }}
            >
              <SelectTrigger
                id="office-level"
                className="w-full"
                aria-invalid={invalid("level")}
                aria-describedby={invalid("level") ? "office-level-error" : "office-level-hint"}
              >
                <SelectValue
                  placeholder={roles.isPending ? "Loading the levels…" : "Choose the level"}
                />
              </SelectTrigger>
              <SelectContent>
                {levels.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {problems.level === undefined ? (
              <FieldDescription id="office-level-hint">
                The level of the role that runs it. It can&apos;t change later.
              </FieldDescription>
            ) : null}
            <FieldError id="office-level-error">{problems.level}</FieldError>
          </Field>
        ) : null}

        <Field data-invalid={invalid("parent")}>
          <FieldLabel htmlFor="office-parent">Under which office</FieldLabel>
          <OfficePicker
            id="office-parent"
            value={draft.root ? null : draft.parent}
            onValueChange={(parent) => {
              set({ parent, ...(parent === null ? {} : { root: false }) });
            }}
            {...(invalid("parent") ? { invalid: true, describedBy: "office-parent-error" } : {})}
          />
          <div className="flex items-center gap-2">
            <Checkbox
              id="office-root"
              checked={draft.root}
              onCheckedChange={(checked) => {
                set({ root: checked, ...(checked ? { parent: null } : {}) });
              }}
            />
            <Label htmlFor="office-root" className="text-sm font-normal">
              A top-level office, under none
            </Label>
          </div>
          <FieldError id="office-parent-error">{problems.parent}</FieldError>
        </Field>

        <Field data-invalid={invalid("territory")}>
          <FieldLabel htmlFor="office-territory">Territory it covers</FieldLabel>
          <TerritoryPicker
            id="office-territory"
            value={draft.hq ? null : draft.territory}
            placeholder="Search a state, district or taluka"
            onValueChange={(territory) => {
              set({ territory, ...(territory === null ? {} : { hq: false }) });
            }}
            aria-invalid={invalid("territory")}
            aria-describedby={invalid("territory") ? "office-territory-error" : undefined}
          />
          <div className="flex items-center gap-2">
            <Checkbox
              id="office-hq"
              checked={draft.hq}
              onCheckedChange={(checked) => {
                set({ hq: checked, ...(checked ? { territory: null } : {}) });
              }}
            />
            <Label htmlFor="office-hq" className="text-sm font-normal">
              An HQ unit, covering no territory
            </Label>
          </div>
          <FieldError id="office-territory-error">{problems.territory}</FieldError>
        </Field>
      </DialogBody>
      <DialogFooter>
        {nothingChanged ? (
          <span className="mr-auto text-xs text-muted-foreground">Nothing changed yet.</span>
        ) : null}
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          disabled={nothingChanged}
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {office === null ? "Add the office" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
