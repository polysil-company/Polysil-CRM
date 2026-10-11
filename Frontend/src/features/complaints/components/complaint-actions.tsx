"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Cancel01Icon, Delete02Icon, Edit02Icon, SentIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState, useWatch } from "react-hook-form";
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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCancelComplaint,
  useCheckComplaint,
  useDeleteComplaint,
  useQcComplaint,
  useSubmitComplaint,
} from "@/features/complaints/api/complaints.mutations";
import { complaintAssigneesQueryOptions } from "@/features/complaints/api/complaints.queries";
import {
  COMPLAINT_SEVERITIES,
  type Complaint,
  type ComplaintSeverity,
} from "@/features/complaints/api/complaints.schemas";
import { complaintRefusal, SEVERITY_LABELS } from "@/features/complaints/lib/complaint-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { COMPLAINT_TEXT_MAX, Refusal, useCloseLater } from "./complaint-dialog-parts";

const log = createLogger({
  file: "features/complaints/components/complaint-actions.tsx",
  dataId: "CMPL-003",
});

const TEXT_MAX = COMPLAINT_TEXT_MAX;

type DialogKind = "check" | "qc" | "cancel" | "delete";

function title(complaint: Complaint): string {
  return complaint.number ?? "this draft";
}

/**
 * CMPL-003…005 · What the user may do on this complaint — only the buttons in its `can`:
 * edit and submit a draft, the manager's check, the QC verdict, cancel, delete a draft never
 * submitted. A step someone else took first closes the dialog and shows the latest.
 */
export function ComplaintActions({
  complaint,
}: {
  complaint: Complaint;
}): React.JSX.Element | null {
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const { can } = complaint;
  const submit = useSubmitComplaint();
  const idempotency = useIdempotencyKey();
  const runSubmit = useAsyncAction({
    action: () =>
      submit.mutateAsync({
        complaintId: complaint.id,
        idempotencyKey: idempotency.keyFor({ submit: complaint.id, count: complaint.submitCount }),
      }),
    logger: log,
    fn: "handleSubmitComplaint",
    dataId: "CMPL-003",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success("Submitted", {
        description: `${saved.number ?? "The complaint"} waits for a manager's check.`,
      });
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      toast.error(view.title, { description: view.message });
    },
  });

  if (!can.edit && !can.submit && !can.check && !can.qc && !can.cancel && !can.delete) return null;
  const close = (): void => {
    setDialog(null);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {can.edit ? (
        <Link
          href={`/complaints/${complaint.id}/edit`}
          className={buttonVariants({ variant: "outline" })}
        >
          <Icon icon={Edit02Icon} />
          Edit
        </Link>
      ) : null}
      {can.submit ? (
        <Button
          state={runSubmit.state}
          loadingLabel="Submitting…"
          successLabel="Submitted"
          errorLabel="Not submitted"
          onClick={() => {
            void runSubmit.run();
          }}
        >
          <Icon icon={SentIcon} />
          {complaint.submitCount > 0 ? "Submit again" : "Submit"}
        </Button>
      ) : null}
      {can.check ? (
        <Button
          onClick={() => {
            setDialog("check");
          }}
        >
          Check
        </Button>
      ) : null}
      {can.qc ? (
        <Button
          onClick={() => {
            setDialog("qc");
          }}
        >
          Give the QC verdict
        </Button>
      ) : null}
      {can.cancel ? (
        <Button
          variant="ghost"
          onClick={() => {
            setDialog("cancel");
          }}
        >
          <Icon icon={Cancel01Icon} />
          Cancel complaint
        </Button>
      ) : null}
      {can.delete ? (
        <Button
          variant="ghost"
          onClick={() => {
            setDialog("delete");
          }}
        >
          <Icon icon={Delete02Icon} />
          Delete draft
        </Button>
      ) : null}

      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent size={dialog === "delete" || dialog === "cancel" ? "sm" : "md"}>
          {dialog === "check" ? <CheckForm complaint={complaint} onClose={close} /> : null}
          {dialog === "qc" ? <QcForm complaint={complaint} onClose={close} /> : null}
          {dialog === "cancel" ? <CancelForm complaint={complaint} onClose={close} /> : null}
          {dialog === "delete" ? <DeleteForm complaint={complaint} onClose={close} /> : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── the manager's check (CMPL-004) ─────────────────────────────────────────────────

interface CheckForm {
  decision: "approve" | "return";
  remark: string;
  severity: ComplaintSeverity;
  ownerId: string;
  internalNote: string;
}

const checkSchema: z.ZodType<CheckForm, CheckForm> = z.object({
  decision: z.enum(["approve", "return"]),
  remark: z
    .string()
    .trim()
    .min(1, "Write a remark. Whoever raised it reads it.")
    .max(TEXT_MAX, "Keep it under 2000 characters."),
  severity: z.enum(COMPLAINT_SEVERITIES),
  ownerId: z.string(),
  internalNote: z.string().max(TEXT_MAX, "Keep it under 2000 characters."),
});

function CheckForm({
  complaint,
  onClose,
}: {
  complaint: Complaint;
  onClose: () => void;
}): React.JSX.Element {
  const check = useCheckComplaint();
  const idempotency = useIdempotencyKey();
  const closeLater = useCloseLater(onClose);
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<CheckForm>({
    resolver: zodResolver(checkSchema),
    defaultValues: {
      decision: "approve",
      remark: "",
      severity: complaint.severity,
      ownerId: complaint.owner?.id ?? "",
      internalNote: "",
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const decision = useWatch({ control: form.control, name: "decision" });
  const approve = decision === "approve";
  const assignees = useQuery({ ...complaintAssigneesQueryOptions(complaint.id), enabled: approve });
  const ownerItems = (assignees.data ?? []).map((person) => ({
    value: person.id,
    label: person.name,
  }));

  const submit = useAsyncAction({
    action: (values: CheckForm) => {
      const body = {
        decision: values.decision,
        remark: values.remark.trim(),
        severity: approve && values.severity !== complaint.severity ? values.severity : null,
        owner_user_id:
          approve && values.ownerId !== "" && values.ownerId !== complaint.owner?.id
            ? values.ownerId
            : null,
        internal_note: values.internalNote.trim() === "" ? null : values.internalNote.trim(),
      };
      return check.mutateAsync({
        complaintId: complaint.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: complaint.id, ...body }),
      });
    },
    logger: log,
    fn: "handleCheckComplaint",
    dataId: "CMPL-004",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(
        saved.status === "under_qc" ? "Approved: sent to QC" : "Returned to whoever raised it",
        {
          description: saved.number ?? undefined,
        },
      );
      closeLater();
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      const remark = view.fields?.remark;
      if (remark !== undefined) form.setError("remark", { type: "server", message: remark });
      else setRefusal({ title: view.title, message: view.message });
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
        <DialogTitle>Check {title(complaint)}</DialogTitle>
        <DialogDescription>
          Approve it for QC, or return it to whoever raised it with what to fix.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="flex flex-col gap-4">
          <Controller
            control={form.control}
            name="decision"
            render={({ field }) => (
              <Field>
                <FieldLabel id="check-decision-label">Decision</FieldLabel>
                <RadioGroup<"approve" | "return">
                  aria-labelledby="check-decision-label"
                  value={field.value}
                  onValueChange={(value) => {
                    field.onChange(value);
                  }}
                  className="flex flex-col gap-2 sm:flex-row sm:gap-6"
                >
                  <label className="flex items-center gap-2 text-sm">
                    <RadioGroupItem value="approve" />
                    Approve, send to QC
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <RadioGroupItem value="return" />
                    Return to fix
                  </label>
                </RadioGroup>
              </Field>
            )}
          />
          <Field data-invalid={errors.remark ? true : undefined}>
            <FieldLabel htmlFor="check-remark">Remark</FieldLabel>
            <Textarea
              id="check-remark"
              rows={3}
              aria-invalid={errors.remark ? true : undefined}
              aria-describedby={errors.remark ? "check-remark-error" : "check-remark-hint"}
              {...form.register("remark")}
            />
            {errors.remark ? null : (
              <FieldDescription id="check-remark-hint">
                Whoever raised it reads this, a dealer included.
              </FieldDescription>
            )}
            <FieldError id="check-remark-error">{errors.remark?.message}</FieldError>
          </Field>
          {approve ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Controller
                control={form.control}
                name="severity"
                render={({ field }) => (
                  <Field>
                    <FieldLabel htmlFor="check-severity">Severity</FieldLabel>
                    <Select
                      items={COMPLAINT_SEVERITIES.map((value) => ({
                        value,
                        label: SEVERITY_LABELS[value],
                      }))}
                      value={field.value}
                      onValueChange={(next) => {
                        if (next !== null) field.onChange(next);
                      }}
                    >
                      <SelectTrigger id="check-severity">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {COMPLAINT_SEVERITIES.map((value) => (
                          <SelectItem key={value} value={value}>
                            {SEVERITY_LABELS[value]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                )}
              />
              <Controller
                control={form.control}
                name="ownerId"
                render={({ field }) => (
                  <Field>
                    <FieldLabel htmlFor="check-owner">
                      Owner
                      <span className="font-normal text-subtle-foreground">(optional)</span>
                    </FieldLabel>
                    <Select
                      items={ownerItems}
                      value={field.value === "" ? null : field.value}
                      disabled={assignees.isPending || assignees.isError}
                      onValueChange={(next) => {
                        if (typeof next === "string") field.onChange(next);
                      }}
                    >
                      <SelectTrigger id="check-owner" aria-describedby="check-owner-hint">
                        <SelectValue
                          placeholder={assignees.isPending ? "Loading…" : "No owner yet"}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {ownerItems.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldDescription id="check-owner-hint">
                      Who follows it up to the end.
                    </FieldDescription>
                  </Field>
                )}
              />
            </div>
          ) : null}
          <Field>
            <FieldLabel htmlFor="check-note">
              Internal note
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="check-note"
              rows={2}
              aria-describedby="check-note-hint"
              {...form.register("internalNote")}
            />
            <FieldDescription id="check-note-hint">
              Staff only. A dealer never sees it.
            </FieldDescription>
          </Field>
        </FieldGroup>
        <Refusal refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant={approve ? "primary" : "destructive"}
          state={submit.state}
          loadingLabel="Saving…"
          successLabel={approve ? "Approved" : "Returned"}
          errorLabel="Not saved"
        >
          {approve ? "Approve" : "Return"}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── the QC verdict (CMPL-005) ──────────────────────────────────────────────────────

interface QcForm {
  verdict: "approved" | "rejected";
  remark: string;
  sampleReceivedOn: string;
  testedOn: string;
  fieldVisitOn: string;
  internalNote: string;
}

function qcSchema(supplyDate: string | null): z.ZodType<QcForm, QcForm> {
  const notAfterToday = (value: string): boolean => value === "" || value <= todayInIndia();
  return z
    .object({
      verdict: z.enum(["approved", "rejected"]),
      remark: z
        .string()
        .trim()
        .min(1, "Write what QC found.")
        .max(TEXT_MAX, "Keep it under 2000 characters."),
      sampleReceivedOn: z.string().refine(notAfterToday, "It can't be after today."),
      testedOn: z.string().refine(notAfterToday, "It can't be after today."),
      fieldVisitOn: z.string().refine(notAfterToday, "It can't be after today."),
      internalNote: z.string().max(TEXT_MAX, "Keep it under 2000 characters."),
    })
    .superRefine((values, ctx) => {
      if (
        supplyDate !== null &&
        values.sampleReceivedOn !== "" &&
        values.sampleReceivedOn < supplyDate
      ) {
        ctx.addIssue({
          code: "custom",
          path: ["sampleReceivedOn"],
          message: "Not before the supply date.",
        });
      }
    });
}

const QC_DATES: readonly {
  name: "sampleReceivedOn" | "testedOn" | "fieldVisitOn";
  label: string;
  api: string;
}[] = [
  { name: "sampleReceivedOn", label: "Sample received on", api: "sample_received_on" },
  { name: "testedOn", label: "Tested on", api: "tested_on" },
  { name: "fieldVisitOn", label: "Field visit on", api: "field_visit_on" },
];

function QcForm({
  complaint,
  onClose,
}: {
  complaint: Complaint;
  onClose: () => void;
}): React.JSX.Element {
  const qc = useQcComplaint();
  const idempotency = useIdempotencyKey();
  const closeLater = useCloseLater(onClose);
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<QcForm>({
    resolver: zodResolver(qcSchema(complaint.supplyDate)),
    defaultValues: {
      verdict: "approved",
      remark: "",
      sampleReceivedOn: "",
      testedOn: "",
      fieldVisitOn: "",
      internalNote: "",
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const verdict = useWatch({ control: form.control, name: "verdict" });

  const submit = useAsyncAction({
    action: (values: QcForm) => {
      const orNull = (value: string): string | null => (value.trim() === "" ? null : value.trim());
      const body = {
        verdict: values.verdict,
        remark: values.remark.trim(),
        sample_received_on: orNull(values.sampleReceivedOn),
        tested_on: orNull(values.testedOn),
        field_visit_on: orNull(values.fieldVisitOn),
        internal_note: orNull(values.internalNote),
      };
      return qc.mutateAsync({
        complaintId: complaint.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: complaint.id, ...body }),
      });
    },
    logger: log,
    fn: "handleQcVerdict",
    dataId: "CMPL-005",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(saved.status === "qc_approved" ? "QC approved" : "QC rejected", {
        description: saved.number ?? undefined,
      });
      closeLater();
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      let placed = false;
      for (const date of QC_DATES) {
        const message = view.fields?.[date.api];
        if (message !== undefined) {
          form.setError(date.name, { type: "server", message });
          placed = true;
        }
      }
      if (!placed) setRefusal({ title: view.title, message: view.message });
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
        <DialogTitle>QC verdict on {title(complaint)}</DialogTitle>
        <DialogDescription>
          Approved: a defect was found, and a remedy follows. Rejected: no defect; it closes.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="flex flex-col gap-4">
          <Controller
            control={form.control}
            name="verdict"
            render={({ field }) => (
              <Field>
                <FieldLabel id="qc-verdict-label">Verdict</FieldLabel>
                <RadioGroup<"approved" | "rejected">
                  aria-labelledby="qc-verdict-label"
                  value={field.value}
                  onValueChange={(value) => {
                    field.onChange(value);
                  }}
                  className="flex flex-col gap-2 sm:flex-row sm:gap-6"
                >
                  <label className="flex items-center gap-2 text-sm">
                    <RadioGroupItem value="approved" />
                    Approved: a defect
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <RadioGroupItem value="rejected" />
                    Rejected: no defect
                  </label>
                </RadioGroup>
              </Field>
            )}
          />
          <Field data-invalid={errors.remark ? true : undefined}>
            <FieldLabel htmlFor="qc-remark">What QC found</FieldLabel>
            <Textarea
              id="qc-remark"
              rows={3}
              aria-invalid={errors.remark ? true : undefined}
              aria-describedby={errors.remark ? "qc-remark-error" : undefined}
              {...form.register("remark")}
            />
            <FieldError id="qc-remark-error">{errors.remark?.message}</FieldError>
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            {QC_DATES.map((date) => (
              <Field key={date.name} data-invalid={errors[date.name] ? true : undefined}>
                <FieldLabel htmlFor={`qc-${date.name}`}>
                  {date.label}
                  <span className="font-normal text-subtle-foreground">(optional)</span>
                </FieldLabel>
                <Input
                  id={`qc-${date.name}`}
                  type="date"
                  max={todayInIndia()}
                  aria-invalid={errors[date.name] ? true : undefined}
                  aria-describedby={errors[date.name] ? `qc-${date.name}-error` : undefined}
                  {...form.register(date.name)}
                />
                <FieldError id={`qc-${date.name}-error`}>{errors[date.name]?.message}</FieldError>
              </Field>
            ))}
          </div>
          <Field>
            <FieldLabel htmlFor="qc-note">
              Internal note
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="qc-note"
              rows={2}
              aria-describedby="qc-note-hint"
              {...form.register("internalNote")}
            />
            <FieldDescription id="qc-note-hint">
              Staff only. A dealer never sees it.
            </FieldDescription>
          </Field>
        </FieldGroup>
        <Refusal refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant={verdict === "approved" ? "primary" : "destructive"}
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {verdict === "approved" ? "Approve" : "Reject"}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── cancel and delete (CMPL-003) ───────────────────────────────────────────────────

const reasonSchema: z.ZodType<{ reason: string }, { reason: string }> = z.object({
  reason: z
    .string()
    .trim()
    .min(1, "Say why it is cancelled.")
    .max(TEXT_MAX, "Keep it under 2000 characters."),
});

function CancelForm({
  complaint,
  onClose,
}: {
  complaint: Complaint;
  onClose: () => void;
}): React.JSX.Element {
  const cancel = useCancelComplaint();
  const idempotency = useIdempotencyKey();
  const closeLater = useCloseLater(onClose);
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<{ reason: string }>({
    resolver: zodResolver(reasonSchema),
    defaultValues: { reason: "" },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const submit = useAsyncAction({
    action: ({ reason }: { reason: string }) => {
      const body = { reason: reason.trim() };
      return cancel.mutateAsync({
        complaintId: complaint.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: complaint.id, ...body }),
      });
    },
    logger: log,
    fn: "handleCancelComplaint",
    dataId: "CMPL-003",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Complaint cancelled");
      closeLater();
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      setRefusal({ title: view.title, message: view.message });
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
        <DialogTitle>Cancel {title(complaint)}?</DialogTitle>
        <DialogDescription>It stays on record as cancelled, with your reason.</DialogDescription>
      </DialogHeader>
      <DialogBody>
        <Field data-invalid={errors.reason ? true : undefined}>
          <FieldLabel htmlFor="complaint-cancel-reason">Reason</FieldLabel>
          <Textarea
            id="complaint-cancel-reason"
            rows={3}
            aria-invalid={errors.reason ? true : undefined}
            aria-describedby={errors.reason ? "complaint-cancel-reason-error" : undefined}
            {...form.register("reason")}
          />
          <FieldError id="complaint-cancel-reason-error">{errors.reason?.message}</FieldError>
        </Field>
        <Refusal refusal={refusal} />
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
          Cancel complaint
        </Button>
      </DialogFooter>
    </form>
  );
}

function DeleteForm({
  complaint,
  onClose,
}: {
  complaint: Complaint;
  onClose: () => void;
}): React.JSX.Element {
  const router = useRouter();
  const remove = useDeleteComplaint();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const submit = useAsyncAction({
    action: () =>
      remove.mutateAsync({
        complaintId: complaint.id,
        idempotencyKey: idempotency.keyFor({ delete: complaint.id }),
      }),
    logger: log,
    fn: "handleDeleteComplaint",
    dataId: "CMPL-003",
    onSuccess: () => {
      toast.success("Draft deleted");
      router.push("/complaints");
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      setRefusal({ title: view.title, message: view.message });
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>Delete this draft?</DialogTitle>
        <DialogDescription>
          It was never submitted, so nothing else refers to it. This can&apos;t be undone.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <Refusal refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          variant="destructive"
          state={submit.state}
          loadingLabel="Deleting…"
          successLabel="Deleted"
          errorLabel="Not deleted"
          onClick={() => {
            setRefusal(null);
            void submit.run();
          }}
        >
          Delete draft
        </Button>
      </DialogFooter>
    </div>
  );
}
