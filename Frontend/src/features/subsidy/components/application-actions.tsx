"use client";

import { Cancel01Icon, Download04Icon, Flag03Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { downloadPims } from "@/features/subsidy/api/subsidy-applications.api";
import {
  useCancelApplication,
  useRecordStage,
} from "@/features/subsidy/api/subsidy-applications.mutations";
import {
  stageDefsQueryOptions,
  stageEntriesQueryOptions,
} from "@/features/subsidy/api/subsidy-applications.queries";
import type { Application, StageField } from "@/features/subsidy/api/subsidy-applications.schemas";
import {
  changedValues,
  fieldProblem,
  initialValues,
  latestValues,
  needsRemark,
} from "@/features/subsidy/lib/stage-form";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { saveFile } from "@/lib/api/save-file";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/subsidy/components/application-actions.tsx",
  dataId: "SUBS-006",
});

/** The scheme whose portal takes the PIMS sheet. */
const PIMS_SCHEME = "GGRC";

type Refusal = { readonly title: string; readonly message: string } | null;

/** A closed or cancelled application refuses entries with 409 status_changed. */
function refusalOf(error: unknown): { refusal: Refusal; stale: boolean } {
  if (isApiError(error) && error.code === "status_changed") {
    return {
      refusal: {
        title: "This application has closed or been cancelled",
        message: "It takes no more entries. The page now shows its latest.",
      },
      stale: true,
    };
  }
  const view = toUserFacingError(error);
  return { refusal: { title: view.title, message: view.description }, stale: false };
}

function RefusalNote({ refusal }: { refusal: Refusal }): React.JSX.Element | null {
  if (refusal === null) return null;
  return (
    <div
      role="alert"
      className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
    >
      <p className="font-medium text-danger">{refusal.title}</p>
      <p className="text-foreground">{refusal.message}</p>
    </div>
  );
}

/**
 * SUBS-006, SUBS-008 · What can be done to an application: record a stage and cancel (for
 * whoever may change applications, while it is open), and download the PIMS sheet (anyone who
 * can see it).
 */
export function ApplicationActions({
  application,
  canWrite,
}: {
  application: Application;
  canWrite: boolean;
}): React.JSX.Element {
  const [dialog, setDialog] = useState<"stage" | "cancel" | null>(null);
  const open = application.status === "open";
  // The PIMS sheet is GGRC's portal format; other schemes have none yet (backend GAP-363).
  const hasPims = application.scheme === PIMS_SCHEME;
  const pims = useAsyncAction({
    action: () => downloadPims(application.id),
    logger: log,
    fn: "handleDownloadPims",
    dataId: "SUBS-008",
    onSuccess: (file) => {
      saveFile(file, `pims-${application.number.replaceAll("/", "-")}.xlsx`);
    },
    onError: (error) => {
      const description =
        isApiError(error) && error.code === "pims_not_for_scheme"
          ? "Only GGRC applications have a PIMS sheet."
          : toUserFacingError(error).description;
      toast.error("The PIMS sheet couldn't be downloaded", { description });
    },
  });
  const close = (): void => {
    setDialog(null);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {hasPims ? (
        <Button
          variant="outline"
          state={pims.state}
          loadingLabel="Downloading…"
          successLabel="Downloaded"
          errorLabel="Not downloaded"
          onClick={() => {
            void pims.run();
          }}
        >
          <Icon icon={Download04Icon} />
          PIMS sheet
        </Button>
      ) : null}
      {canWrite && open ? (
        <>
          <Button
            variant="outline"
            onClick={() => {
              setDialog("cancel");
            }}
          >
            <Icon icon={Cancel01Icon} />
            Cancel application
          </Button>
          <Button
            onClick={() => {
              setDialog("stage");
            }}
          >
            <Icon icon={Flag03Icon} />
            Record stage
          </Button>
        </>
      ) : null}

      <Dialog
        open={dialog !== null}
        onOpenChange={(next) => {
          if (!next) close();
        }}
      >
        <DialogContent size={dialog === "stage" ? "lg" : "sm"}>
          {dialog === "stage" ? (
            <RecordStageForm application={application} onClose={close} />
          ) : null}
          {dialog === "cancel" ? (
            <CancelApplicationForm application={application} onClose={close} />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── record a stage ────────────────────────────────────────────────────────────────

function RecordStageForm({
  application,
  onClose,
}: {
  application: Application;
  onClose: () => void;
}): React.JSX.Element {
  const stages = useQuery(stageDefsQueryOptions(application.scheme));
  const entries = useQuery(stageEntriesQueryOptions(application.id));
  const defs = stages.data ?? [];
  const latest = latestValues(entries.data ?? []);
  const today = todayInIndia();
  const [stageCode, setStageCode] = useState(application.stage.code);
  const stage = defs.find((item) => item.code === stageCode) ?? null;
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [occurredOn, setOccurredOn] = useState(today);
  const [remark, setRemark] = useState("");
  const [shown, setShown] = useState(false);
  const [serverProblems, setServerProblems] = useState<Readonly<Record<string, string>>>({});
  const [refusal, setRefusal] = useState<Refusal>(null);
  const record = useRecordStage();
  const idempotency = useIdempotencyKey();

  // The form starts from what each field holds now, once the stages and history are in.
  const formValues = values ?? (stage === null ? {} : initialValues(stage, latest));
  const remarkNeeded = stage !== null && needsRemark(stage, application.stage.seq);

  const problems: Record<string, string> = {};
  if (stage !== null) {
    for (const field of stage.fields) {
      const problem = fieldProblem(field, formValues[field.key] ?? "", today);
      if (problem !== null) problems[`values.${field.key}`] = problem;
    }
  }
  if (occurredOn === "") problems.occurred_on = "Enter the date it happened.";
  else if (occurredOn > today) problems.occurred_on = "Not after today.";
  if (remarkNeeded && remark.trim() === "") {
    problems.remark =
      stage.seq === application.stage.seq
        ? "Say why this stage is recorded again."
        : "Say why the application goes back to this stage.";
  }
  const visible: Readonly<Record<string, string>> = shown
    ? { ...serverProblems, ...problems }
    : serverProblems;

  const submit = useAsyncAction({
    action: () => {
      if (stage === null) throw new Error("No stage chosen");
      const body = {
        stage_code: stage.code,
        occurred_on: occurredOn,
        values: changedValues(stage, formValues, latest),
        remark: remark.trim() === "" ? null : remark.trim(),
      };
      return record.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleRecordStage",
    dataId: "SUBS-006",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(`${saved.stage.name} recorded`, {
        description:
          saved.status === "full_fp_received"
            ? "Every payment is in: the application has closed."
            : saved.number,
      });
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null) {
        setServerProblems(fields);
        setRefusal({
          title: "Some fields need correcting",
          message: "The marked fields say what to change.",
        });
        return;
      }
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next?.title ?? "Not recorded", { description: next?.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });

  const loading = stages.isPending || entries.isPending;

  return (
    <form
      noValidate
      aria-label="Record stage"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (Object.keys(problems).length > 0 || stage === null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Record stage</DialogTitle>
        <DialogDescription>
          {application.number} is at {application.stage.seq}. {application.stage.name}. Any stage
          can be recorded as it happens at GGRC; only the fields you change are sent.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {stages.isError || entries.isError ? (
          <RefusalNote
            refusal={{
              title: "The stages couldn't be loaded",
              message: "Close this and try again.",
            }}
          />
        ) : null}
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="stage-code">Stage</FieldLabel>
            <Select
              items={defs.map((item) => ({
                value: item.code,
                label: `${String(item.seq)}. ${item.name}`,
              }))}
              value={stageCode}
              disabled={loading}
              onValueChange={(next) => {
                if (typeof next !== "string") return;
                setStageCode(next);
                setValues(null);
                setServerProblems({});
              }}
            >
              <SelectTrigger id="stage-code" className="w-full">
                <SelectValue placeholder={loading ? "Loading stages…" : "Choose a stage"} />
              </SelectTrigger>
              <SelectContent>
                {defs.map((item) => (
                  <SelectItem key={item.code} value={item.code}>
                    {item.seq}. {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field data-invalid={visible.occurred_on === undefined ? undefined : true}>
            <FieldLabel htmlFor="stage-occurred-on">Happened on</FieldLabel>
            <Input
              id="stage-occurred-on"
              type="date"
              max={today}
              value={occurredOn}
              aria-invalid={visible.occurred_on === undefined ? undefined : true}
              aria-describedby={
                visible.occurred_on === undefined ? undefined : "stage-occurred-on-error"
              }
              onChange={(event) => {
                setOccurredOn(event.target.value);
              }}
            />
            <FieldError id="stage-occurred-on-error">{visible.occurred_on}</FieldError>
          </Field>

          {stage === null
            ? null
            : stage.fields.map((field) => (
                <StageFieldInput
                  key={`${stage.code}-${field.key}`}
                  field={field}
                  value={formValues[field.key] ?? ""}
                  today={today}
                  error={visible[`values.${field.key}`]}
                  onChange={(next) => {
                    setValues({ ...formValues, [field.key]: next });
                  }}
                />
              ))}
          {stage !== null && stage.fields.length === 0 ? (
            <p className="text-sm text-muted-foreground sm:col-span-2">
              This stage has no fields: recording it notes the date.
            </p>
          ) : null}

          <Field
            data-invalid={visible.remark === undefined ? undefined : true}
            className="sm:col-span-2"
          >
            <FieldLabel htmlFor="stage-remark">
              Remark
              {remarkNeeded ? null : (
                <span className="font-normal text-muted-foreground">(optional)</span>
              )}
            </FieldLabel>
            <Textarea
              id="stage-remark"
              maxLength={1000}
              value={remark}
              aria-invalid={visible.remark === undefined ? undefined : true}
              aria-describedby={
                visible.remark === undefined ? "stage-remark-hint" : "stage-remark-error"
              }
              onChange={(event) => {
                setRemark(event.target.value);
              }}
            />
            {visible.remark === undefined ? (
              <FieldDescription id="stage-remark-hint">
                {remarkNeeded
                  ? "Needed going back, or recording the current stage again."
                  : "What happened, for whoever reads the history."}
              </FieldDescription>
            ) : null}
            <FieldError id="stage-remark-error">{visible.remark}</FieldError>
          </Field>
        </FieldGroup>
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          disabled={loading || stage === null}
          state={submit.state}
          loadingLabel="Recording…"
          successLabel="Recorded"
          errorLabel="Not recorded"
        >
          Record stage
        </Button>
      </DialogFooter>
    </form>
  );
}

function StageFieldInput({
  field,
  value,
  today,
  error,
  onChange,
}: {
  field: StageField;
  value: string;
  today: string;
  error: string | undefined;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const id = `stage-field-${field.key}`;
  const aria = {
    id,
    "aria-invalid": error === undefined ? undefined : true,
    "aria-describedby": error === undefined ? undefined : `${id}-error`,
  } as const;
  return (
    <Field
      data-invalid={error === undefined ? undefined : true}
      className={field.type === "text" ? "sm:col-span-2" : undefined}
    >
      <FieldLabel htmlFor={id}>
        {field.label}
        {field.required ? null : (
          <span className="font-normal text-muted-foreground">(optional)</span>
        )}
      </FieldLabel>
      {field.type === "date" ? (
        <Input
          {...aria}
          type="date"
          max={today}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      ) : field.type === "amount" ? (
        <InputGroup>
          <InputGroupAddon>₹</InputGroupAddon>
          <InputGroupInput
            {...aria}
            inputMode="decimal"
            autoComplete="off"
            className="tabular-nums"
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
            }}
          />
        </InputGroup>
      ) : (
        <Input
          {...aria}
          maxLength={500}
          autoComplete="off"
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      )}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}

// ── cancel ────────────────────────────────────────────────────────────────────────

function CancelApplicationForm({
  application,
  onClose,
}: {
  application: Application;
  onClose: () => void;
}): React.JSX.Element {
  const [reason, setReason] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<Refusal>(null);
  const cancel = useCancelApplication();
  const idempotency = useIdempotencyKey();
  const problem = reason.trim() === "" ? "Say why it is cancelled." : null;
  const submit = useAsyncAction({
    action: () => {
      const body = { reason: reason.trim() };
      return cancel.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleCancelApplication",
    dataId: "SUBS-006",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Application cancelled", {
        description: "The lead can start a new application.",
      });
      onClose();
    },
    onError: (error) => {
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next?.title ?? "Not cancelled", { description: next?.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });
  const error = shown ? problem : null;

  return (
    <form
      noValidate
      aria-label="Cancel application"
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
        <DialogTitle>Cancel {application.number}?</DialogTitle>
        <DialogDescription>
          It takes no more entries, and the lead can start a new application.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        <Field data-invalid={error === null ? undefined : true}>
          <FieldLabel htmlFor="cancel-reason">Reason</FieldLabel>
          <Textarea
            id="cancel-reason"
            maxLength={500}
            value={reason}
            aria-invalid={error === null ? undefined : true}
            aria-describedby={error === null ? undefined : "cancel-reason-error"}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
          <FieldError id="cancel-reason-error">{error}</FieldError>
        </Field>
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={submit.state}
          loadingLabel="Cancelling…"
          successLabel="Cancelled"
          errorLabel="Not cancelled"
        >
          Cancel application
        </Button>
      </DialogFooter>
    </form>
  );
}
