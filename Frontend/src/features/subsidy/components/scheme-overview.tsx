"use client";

import {
  Alert02Icon,
  CheckmarkCircle02Icon,
  Edit02Icon,
  Link01Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import {
  useCreateScheme,
  usePatchScheme,
  useRenameStage,
} from "@/features/subsidy/api/subsidy-schemes.mutations";
import { schemeDetailQueryOptions } from "@/features/subsidy/api/subsidy-schemes.queries";
import type {
  MissingTable,
  SchemeDetail,
  SchemeRow,
} from "@/features/subsidy/api/subsidy-schemes.schemas";
import { SYSTEM_TYPES, type SystemType } from "@/features/subsidy/api/subsidy.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { readMissing } from "@/features/subsidy/lib/scheme-readiness";
import { SYSTEM_LABELS } from "@/features/subsidy/lib/subsidy-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/subsidy/components/scheme-overview.tsx",
  dataId: "SUBS-014",
});

/** The refusals a scheme write can meet, in words. */
const SCHEME_REFUSALS: Readonly<Record<string, string>> = {
  code_taken: "Another scheme already has that code.",
  state_has_scheme: "That state already has an active scheme.",
  unlinked_scheme_exists: "Link the scheme without a state to its state first.",
  state_fixed: "This scheme's state is already set and can't change.",
};

function refusalText(error: unknown): string {
  if (isApiError(error) && error.code !== undefined) {
    const known = SCHEME_REFUSALS[error.code];
    if (known !== undefined) return known;
  }
  const fields = readFieldErrors(error);
  if (fields !== null) {
    return Object.entries(fields)
      .map(([path, message]) => `${path}: ${message}`)
      .join(" · ");
  }
  return toUserFacingError(error).title;
}

/**
 * SUBS-014 · A scheme at a glance: whether each system can calculate, and what it still lacks
 * (each linked to the table that fills it); its stages, which an administrator may rename; and
 * switching it off. A scheme with no state is called out first: another state's scheme waits
 * until it is linked.
 */
export function SchemeOverview({
  scheme,
  row,
  unlinked,
  on,
  canEdit,
  onOpenTable,
}: {
  scheme: string;
  /** The scheme's list row, for its application count. */
  row: SchemeRow | null;
  /** A scheme with no state, when one exists. */
  unlinked: SchemeRow | null;
  on: string | null;
  canEdit: boolean;
  onOpenTable: (table: MissingTable) => void;
}): React.JSX.Element {
  const detail = useQuery(schemeDetailQueryOptions(scheme, on));
  const [dialog, setDialog] = useState<"switch" | "link" | null>(null);
  const [renaming, setRenaming] = useState<SchemeDetail["stages"][number] | null>(null);
  const close = (): void => {
    setDialog(null);
    setRenaming(null);
  };

  return (
    <section aria-label="Scheme overview" className="flex flex-col gap-4">
      {unlinked !== null ? (
        <Notice tone="warning">
          <p className="font-medium">
            Link {unlinked.code} to its state before adding another state&apos;s scheme.
          </p>
          <p>A scheme with no state can&apos;t tell which leads it applies to.</p>
          {canEdit && unlinked.code === scheme ? (
            <Button
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() => {
                setDialog("link");
              }}
            >
              <Icon icon={Link01Icon} />
              Link {unlinked.code} to a state
            </Button>
          ) : null}
        </Notice>
      ) : null}

      {detail.status === "pending" ? (
        <div className="grid gap-4 lg:grid-cols-3" aria-hidden>
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      ) : detail.status === "error" ? (
        <ErrorState
          error={detail.error}
          onRetry={() => {
            void detail.refetch();
          }}
        />
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold text-foreground">{detail.data.name}</h2>
                <Badge
                  variant={
                    !detail.data.active ? "neutral" : detail.data.ready ? "success" : "warning"
                  }
                  dot
                >
                  {!detail.data.active ? "Switched off" : detail.data.ready ? "Ready" : "Not ready"}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                {detail.data.code} · {detail.data.state?.name ?? "No state yet"}
                {row === null
                  ? ""
                  : ` · ${formatNumber(row.applications)} application${row.applications === 1 ? "" : "s"}`}{" "}
                · checked for {formatBusinessDay(detail.data.on)}
              </p>
            </div>
            {canEdit ? (
              <Button
                variant="outline"
                onClick={() => {
                  setDialog("switch");
                }}
              >
                {detail.data.active ? "Switch off" : "Switch on"}
              </Button>
            ) : null}
          </div>

          <ul aria-label="Systems" className="grid gap-4 lg:grid-cols-3">
            {detail.data.systems.map((system) => (
              <li key={system.systemType}>
                <Card className="h-full">
                  <CardHeader>
                    <div className="flex flex-col gap-0.5">
                      <CardTitle level={3}>{SYSTEM_LABELS[system.systemType]}</CardTitle>
                      <CardDescription>
                        {system.ready
                          ? "Can calculate"
                          : `${String(system.missing.length)} thing${system.missing.length === 1 ? "" : "s"} to fill`}
                      </CardDescription>
                    </div>
                    <Icon
                      icon={system.ready ? CheckmarkCircle02Icon : Alert02Icon}
                      className={system.ready ? "text-success" : "text-warning"}
                    />
                  </CardHeader>
                  <CardContent>
                    {system.ready ? (
                      <p className="text-sm text-muted-foreground">
                        Every table it reads is in force.
                      </p>
                    ) : (
                      <ol
                        aria-label={`What ${SYSTEM_LABELS[system.systemType]} lacks`}
                        className="flex flex-col gap-1.5 text-sm"
                      >
                        {system.missing.map((item) => {
                          const missing = readMissing(item);
                          return (
                            <li key={item} className="flex items-center justify-between gap-2">
                              <span className="text-foreground">{missing.text}</span>
                              {missing.table === null ? null : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={`Open the table for ${missing.text.toLowerCase()}`}
                                  onClick={() => {
                                    if (missing.table !== null) onOpenTable(missing.table);
                                  }}
                                >
                                  Open
                                </Button>
                              )}
                            </li>
                          );
                        })}
                      </ol>
                    )}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>

          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>Stages</CardTitle>
                <CardDescription>
                  {detail.data.stages.some((stage) => stage.active)
                    ? "The steps an application records, in order. Names can change; the steps can't yet."
                    : "No active stage: applications can't start. Contact support."}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <ol aria-label="Stages" className="flex flex-col divide-y divide-border">
                {detail.data.stages.map((stage) => (
                  <li
                    key={stage.code}
                    className="flex items-center justify-between gap-3 py-2 text-sm"
                  >
                    <span className={stage.active ? "text-foreground" : "text-muted-foreground"}>
                      {stage.seq}. {stage.name}
                      {stage.active ? "" : " (off)"}
                    </span>
                    {canEdit ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Rename ${stage.name}`}
                        onClick={() => {
                          setRenaming(stage);
                        }}
                      >
                        <Icon icon={Edit02Icon} />
                        Rename
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </>
      )}

      <Dialog
        open={dialog !== null || renaming !== null}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent size="sm">
          {dialog === "switch" && detail.data !== undefined ? (
            <SwitchForm detail={detail.data} row={row} onClose={close} />
          ) : dialog === "link" ? (
            <LinkStateForm code={scheme} onClose={close} />
          ) : renaming !== null ? (
            <RenameStageForm code={scheme} stage={renaming} onClose={close} />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function SwitchForm({
  detail,
  row,
  onClose,
}: {
  detail: SchemeDetail;
  row: SchemeRow | null;
  onClose: () => void;
}): React.JSX.Element {
  const patch = usePatchScheme();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<string | null>(null);
  const next = !detail.active;
  const submit = useAsyncAction({
    action: () => {
      const body = { is_active: next };
      return patch.mutateAsync({
        code: detail.code,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleSwitchScheme",
    dataId: "SUBS-014",
    onSuccess: () => {
      idempotency.reset();
      toast.success(next ? `${detail.code} switched on` : `${detail.code} switched off`);
      onClose();
    },
    onError: (error) => {
      setRefusal(refusalText(error));
    },
  });
  const count = row?.applications ?? 0;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>
          {next ? "Switch on" : "Switch off"} {detail.code}?
        </DialogTitle>
        <DialogDescription>
          {next
            ? `Leads in ${detail.state?.name ?? "its state"} can start applications under it again.`
            : `No new application can start under it. Its ${formatNumber(count)} application${count === 1 ? "" : "s"} carry on as they are.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it {detail.active ? "on" : "off"}
        </DialogClose>
        <Button
          variant={next ? "primary" : "destructive"}
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
          onClick={() => {
            setRefusal(null);
            void submit.run();
          }}
        >
          {next ? "Switch on" : "Switch off"}
        </Button>
      </DialogFooter>
    </div>
  );
}

function LinkStateForm({
  code,
  onClose,
}: {
  code: string;
  onClose: () => void;
}): React.JSX.Element {
  const patch = usePatchScheme();
  const idempotency = useIdempotencyKey();
  const [state, setState] = useState<TerritoryChoice | null>(null);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const submit = useAsyncAction({
    action: () => {
      const body = { state_territory_id: state?.id ?? "" };
      return patch.mutateAsync({ code, body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleLinkScheme",
    dataId: "SUBS-014",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`${code} linked to ${state?.name ?? "its state"}`);
      onClose();
    },
    onError: (error) => {
      setRefusal(refusalText(error));
    },
  });
  const error = shown && state === null ? "Choose the state." : null;
  return (
    <form
      noValidate
      aria-label={`Link ${code} to a state`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (state === null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Link {code} to a state</DialogTitle>
        <DialogDescription>Once set, the state can&apos;t change.</DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        <Field data-invalid={error === null ? undefined : true}>
          <FieldLabel htmlFor="link-state">State</FieldLabel>
          <TerritoryPicker
            id="link-state"
            value={state}
            levels={["state"]}
            placeholder="Search a state"
            onValueChange={setState}
            aria-invalid={error === null ? undefined : true}
            aria-describedby={error === null ? undefined : "link-state-error"}
          />
          <FieldError id="link-state-error">{error}</FieldError>
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
          loadingLabel="Linking…"
          successLabel="Linked"
          errorLabel="Not linked"
        >
          Link
        </Button>
      </DialogFooter>
    </form>
  );
}

function RenameStageForm({
  code,
  stage,
  onClose,
}: {
  code: string;
  stage: SchemeDetail["stages"][number];
  onClose: () => void;
}): React.JSX.Element {
  const rename = useRenameStage();
  const idempotency = useIdempotencyKey();
  const [name, setName] = useState(stage.name);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const trimmed = name.trim();
  const problem =
    trimmed === ""
      ? "Give the stage a name."
      : trimmed === stage.name
        ? "That's its name already."
        : null;
  const submit = useAsyncAction({
    action: () =>
      rename.mutateAsync({
        code,
        stageCode: stage.code,
        name: trimmed,
        idempotencyKey: idempotency.keyFor({ stage: stage.code, name: trimmed }),
      }),
    logger: log,
    fn: "handleRenameStage",
    dataId: "SUBS-014",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Stage renamed", { description: `${String(stage.seq)}. ${trimmed}` });
      onClose();
    },
    onError: (error) => {
      setRefusal(refusalText(error));
    },
  });
  const error = shown ? problem : null;
  return (
    <form
      noValidate
      aria-label="Rename stage"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (problem !== null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Rename stage {stage.seq}</DialogTitle>
        <DialogDescription>
          The name every application of {code} shows; what was recorded stays.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        <Field data-invalid={error === null ? undefined : true}>
          <FieldLabel htmlFor="stage-name">Name</FieldLabel>
          <Input
            id="stage-name"
            maxLength={120}
            value={name}
            aria-invalid={error === null ? undefined : true}
            aria-describedby={error === null ? undefined : "stage-name-error"}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
          <FieldError id="stage-name-error">{error}</FieldError>
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
          Rename
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── a new scheme ──────────────────────────────────────────────────────────────────

const CODE_PATTERN = /^[A-Z0-9_]{2,20}$/;

/** A refusal's field on the wire, as the form names it. */
const FORM_FIELDS: Readonly<Record<string, string>> = {
  code: "code",
  name: "name",
  state_territory_id: "state",
  template: "template",
  systems: "systems",
};

/** The refusals that belong to one input rather than the whole form. */
const FIELD_REFUSALS: Readonly<Record<string, string>> = {
  code_taken: "code",
  state_has_scheme: "state",
};

/** A create refusal split into what marks an input and what is said above the buttons. */
function readCreateRefusal(error: unknown): {
  fields: Record<string, string>;
  refusal: string | null;
} {
  if (isApiError(error) && error.code !== undefined) {
    const field = FIELD_REFUSALS[error.code];
    const text = SCHEME_REFUSALS[error.code];
    if (field !== undefined && text !== undefined)
      return { fields: { [field]: text }, refusal: null };
  }
  const wire = readFieldErrors(error);
  if (wire !== null) {
    const fields: Record<string, string> = {};
    const rest: string[] = [];
    for (const [path, message] of Object.entries(wire)) {
      const field = FORM_FIELDS[path];
      if (field === undefined) rest.push(`${path}: ${message}`);
      else fields[field] = message;
    }
    return { fields, refusal: rest.length === 0 ? null : rest.join(" · ") };
  }
  return { fields: {}, refusal: refusalText(error) };
}

/**
 * SUBS-014 · Set up another state's scheme: its code, name and state, the scheme whose engine
 * settings and stages it starts from (no figure is copied), and the systems it runs. It starts
 * not ready; the overview then lists what to fill.
 */
export function NewSchemeForm({
  schemes,
  onCreated,
}: {
  schemes: readonly SchemeRow[];
  onCreated: (code: string) => void;
}): React.JSX.Element {
  const create = useCreateScheme();
  const idempotency = useIdempotencyKey();
  const templates = schemes.filter((scheme) => scheme.active);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [state, setState] = useState<TerritoryChoice | null>(null);
  const [template, setTemplate] = useState(templates[0]?.code ?? "GGRC");
  const templateSystems: readonly SystemType[] =
    schemes.find((scheme) => scheme.code === template)?.systems ?? SYSTEM_TYPES;
  const [systems, setSystems] = useState<readonly SystemType[]>(templateSystems);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [serverFields, setServerFields] = useState<Record<string, string>>({});

  const upper = code.trim().toUpperCase();
  const problems: Record<string, string> = {};
  if (!CODE_PATTERN.test(upper)) problems.code = "2 to 20 letters, digits or _, e.g. UPMIS.";
  else if (schemes.some((scheme) => scheme.code === upper))
    problems.code = "Another scheme has that code.";
  if (name.trim() === "") problems.name = "Name the scheme.";
  if (state === null) problems.state = "Choose the state it serves.";
  if (systems.length === 0) problems.systems = "Choose at least one system.";
  const visible: Record<string, string | undefined> = shown
    ? { ...serverFields, ...problems }
    : serverFields;

  const submit = useAsyncAction({
    action: () => {
      const body = {
        code: upper,
        name: name.trim(),
        state_territory_id: state?.id ?? "",
        template,
        systems: systems.length === templateSystems.length ? null : systems,
      };
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleCreateScheme",
    dataId: "SUBS-014",
    onSuccess: (created) => {
      idempotency.reset();
      toast.success(`${created.code} set up`, {
        description: "It starts empty: fill what the overview lists, then it's ready.",
      });
      onCreated(created.code);
    },
    onError: (error) => {
      const read = readCreateRefusal(error);
      setServerFields(read.fields);
      setRefusal(read.refusal);
    },
  });

  return (
    <form
      noValidate
      aria-label="New scheme"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        setServerFields({});
        if (Object.keys(problems).length > 0) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>New scheme</DialogTitle>
        <DialogDescription>
          Another state&apos;s subsidy scheme. It copies a scheme&apos;s settings and stages, never
          its figures.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={visible.code === undefined ? undefined : true}>
            <FieldLabel htmlFor="scheme-code">Code</FieldLabel>
            <Input
              id="scheme-code"
              maxLength={20}
              autoComplete="off"
              className="font-mono uppercase"
              placeholder="UPMIS"
              value={code}
              aria-invalid={visible.code === undefined ? undefined : true}
              aria-describedby={visible.code === undefined ? undefined : "scheme-code-error"}
              onChange={(event) => {
                setCode(event.target.value);
              }}
            />
            <FieldError id="scheme-code-error">{visible.code}</FieldError>
          </Field>
          <Field data-invalid={visible.name === undefined ? undefined : true}>
            <FieldLabel htmlFor="scheme-name">Name</FieldLabel>
            <Input
              id="scheme-name"
              maxLength={200}
              placeholder="UP Micro Irrigation"
              value={name}
              aria-invalid={visible.name === undefined ? undefined : true}
              aria-describedby={visible.name === undefined ? undefined : "scheme-name-error"}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
            <FieldError id="scheme-name-error">{visible.name}</FieldError>
          </Field>
          <Field data-invalid={visible.state === undefined ? undefined : true}>
            <FieldLabel htmlFor="scheme-state">State</FieldLabel>
            <TerritoryPicker
              id="scheme-state"
              value={state}
              levels={["state"]}
              placeholder="Search a state"
              onValueChange={setState}
              aria-invalid={visible.state === undefined ? undefined : true}
              aria-describedby={visible.state === undefined ? undefined : "scheme-state-error"}
            />
            <FieldError id="scheme-state-error">{visible.state}</FieldError>
          </Field>
          <Field data-invalid={visible.template === undefined ? undefined : true}>
            <FieldLabel htmlFor="scheme-template">Start from</FieldLabel>
            <Select
              items={templates.map((scheme) => ({ value: scheme.code, label: scheme.code }))}
              value={template}
              onValueChange={(next) => {
                if (typeof next !== "string") return;
                setTemplate(next);
                setSystems(schemes.find((scheme) => scheme.code === next)?.systems ?? SYSTEM_TYPES);
              }}
            >
              <SelectTrigger id="scheme-template" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {templates.map((scheme) => (
                  <SelectItem key={scheme.code} value={scheme.code}>
                    {scheme.code} · {scheme.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription>Its engine settings and stages; no figures.</FieldDescription>
            <FieldError>{visible.template}</FieldError>
          </Field>
        </div>
        <fieldset
          className="flex flex-col gap-2"
          aria-describedby={visible.systems === undefined ? undefined : "scheme-systems-error"}
        >
          <legend className="text-sm font-medium text-foreground">Systems</legend>
          <div className="flex flex-wrap gap-4">
            {templateSystems.map((system) => (
              <div key={system} className="flex items-center gap-2">
                <Checkbox
                  id={`scheme-system-${system}`}
                  checked={systems.includes(system)}
                  onCheckedChange={(checked) => {
                    setSystems((current) =>
                      checked ? [...current, system] : current.filter((item) => item !== system),
                    );
                  }}
                />
                <Label htmlFor={`scheme-system-${system}`} className="text-sm">
                  {SYSTEM_LABELS[system]}
                </Label>
              </div>
            ))}
          </div>
          <FieldError id="scheme-systems-error">{visible.systems}</FieldError>
        </fieldset>
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
          loadingLabel="Setting up…"
          successLabel="Set up"
          errorLabel="Not set up"
        >
          Set up the scheme
        </Button>
      </DialogFooter>
    </form>
  );
}
