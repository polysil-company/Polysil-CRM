"use client";

import {
  CheckmarkBadge01Icon,
  Edit02Icon,
  Link01Icon,
  MoreVerticalIcon,
  SentIcon,
} from "@hugeicons/core-free-icons";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import {
  useDecideDealerApplication,
  useRenewDealerApplicationLink,
  useSubmitDealerApplication,
  useWithdrawDealerApplication,
} from "@/features/dealer-applications/api/dealer-applications.mutations";
import {
  DECISIONS,
  type DealerApplication,
  type Decision,
} from "@/features/dealer-applications/api/dealer-applications.schemas";
import { DECISION_LABELS } from "@/features/dealer-applications/lib/dealer-application-labels";
import { ParentPicker, type ParentChoice } from "@/features/partners/components/parent-picker";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import { ApplyLink } from "./apply-link";
import { refusalOf, RefusalNote, type Refusal } from "./dealer-application-refusals";
import { EditDealerApplication } from "./edit-dealer-application";

const log = createLogger({
  file: "features/dealer-applications/components/dealer-application-actions.tsx",
  dataId: "CHNL-007",
});

type DialogKind = "edit" | "link" | "withdraw" | "decide";

/**
 * CHNL-007 · What the reader may do, from the application's `can`: fill it in, submit it for
 * the applicant, send a new link, withdraw it, and (a State Manager or above who didn't start
 * it) decide.
 */
export function DealerApplicationActions({
  application,
}: {
  application: DealerApplication;
}): React.JSX.Element | null {
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const { can } = application;
  const submittable =
    can.edit && (application.status === "draft" || application.status === "returned");
  const close = (): void => {
    setDialog(null);
  };

  if (!can.edit && !can.decide && !can.withdraw && !can.renew) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {can.edit ? (
        <Button
          variant="outline"
          onClick={() => {
            setDialog("edit");
          }}
        >
          <Icon icon={Edit02Icon} />
          Edit details
        </Button>
      ) : null}
      {submittable ? <SubmitButton application={application} /> : null}
      {can.decide ? (
        <Button
          onClick={() => {
            setDialog("decide");
          }}
        >
          <Icon icon={CheckmarkBadge01Icon} />
          Decide
        </Button>
      ) : null}
      {can.renew || can.withdraw ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="ghost" size="icon-md" aria-label="More actions" />}
          >
            <Icon icon={MoreVerticalIcon} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {can.renew ? (
              <DropdownMenuItem
                onClick={() => {
                  setDialog("link");
                }}
              >
                <Icon icon={Link01Icon} />
                New link…
              </DropdownMenuItem>
            ) : null}
            {can.withdraw ? (
              <DropdownMenuItem
                variant="destructive"
                onClick={() => {
                  setDialog("withdraw");
                }}
              >
                Withdraw…
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}

      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent size={dialog === "edit" ? "lg" : "sm"}>
          {dialog === "edit" ? (
            <EditDealerApplication application={application} onClose={close} />
          ) : null}
          {dialog === "link" ? <RenewLink application={application} onClose={close} /> : null}
          {dialog === "withdraw" ? (
            <WithdrawForm application={application} onClose={close} />
          ) : null}
          {dialog === "decide" ? <DecideForm application={application} onClose={close} /> : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SubmitButton({ application }: { application: DealerApplication }): React.JSX.Element {
  const mutation = useSubmitDealerApplication();
  const idempotency = useIdempotencyKey();
  const submit = useAsyncAction({
    action: () =>
      mutation.mutateAsync({
        applicationId: application.id,
        idempotencyKey: idempotency.keyFor({ submit: application.id }),
      }),
    logger: log,
    fn: "handleSubmitDealerApplication",
    dataId: "CHNL-007",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Application submitted", {
        description: "A State Manager or above decides it next.",
      });
    },
    onError: (error) => {
      const { refusal } = refusalOf(error);
      toast.error(refusal.title, { description: refusal.message });
    },
  });
  return (
    <Button
      variant="outline"
      // the notice above says what is still missing
      disabled={application.missing.length > 0 && submit.state === "idle"}
      state={submit.state}
      loadingLabel="Submitting…"
      successLabel="Submitted"
      errorLabel="Not submitted"
      onClick={() => {
        void submit.run();
      }}
    >
      <Icon icon={SentIcon} />
      Submit for them
    </Button>
  );
}

/** A new link for 30 days; the old one, and any open applicant session, stop working. */
function RenewLink({
  application,
  onClose,
}: {
  application: DealerApplication;
  onClose: () => void;
}): React.JSX.Element {
  const mutation = useRenewDealerApplicationLink();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const renew = useAsyncAction({
    action: () =>
      mutation.mutateAsync({
        applicationId: application.id,
        idempotencyKey: idempotency.keyFor({ renew: application.id }),
      }),
    logger: log,
    fn: "handleRenewDealerApplicationLink",
    dataId: "CHNL-007",
    onSuccess: (renewed) => {
      idempotency.reset();
      setUrl(renewed.applyUrl);
    },
    onError: (error) => {
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next.title, { description: next.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>{url === null ? "Send a new link?" : "New link"}</DialogTitle>
        <DialogDescription>
          {url === null
            ? "The old link, and anyone filling it in now, stop working. The new one works for 30 days."
            : `Send ${application.contactName} this link.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        {url === null ? null : (
          <ApplyLink url={url} name={application.contactName} mobile={application.mobile} />
        )}
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        {url === null ? (
          <>
            <DialogClose
              render={<Button type="button" variant="outline" disabled={renew.isBusy} />}
            >
              Cancel
            </DialogClose>
            <Button
              state={renew.state}
              loadingLabel="Making…"
              successLabel="Made"
              errorLabel="Not made"
              onClick={() => {
                setRefusal(null);
                void renew.run();
              }}
            >
              Make a new link
            </Button>
          </>
        ) : (
          <DialogClose render={<Button type="button" />}>Done</DialogClose>
        )}
      </DialogFooter>
    </>
  );
}

function WithdrawForm({
  application,
  onClose,
}: {
  application: DealerApplication;
  onClose: () => void;
}): React.JSX.Element {
  const mutation = useWithdrawDealerApplication();
  const idempotency = useIdempotencyKey();
  const [remark, setRemark] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const problem = remark.trim() === "" ? "Say why it is withdrawn." : null;

  const withdraw = useAsyncAction({
    action: () => {
      const body = { remark: remark.trim() };
      return mutation.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleWithdrawDealerApplication",
    dataId: "CHNL-007",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Application withdrawn", { description: "Its link stops working." });
      onClose();
    },
    onError: (error) => {
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next.title, { description: next.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });

  return (
    <form
      noValidate
      aria-label="Withdraw the application"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (problem !== null) return;
        void withdraw.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Withdraw {application.firmName}&apos;s application?</DialogTitle>
        <DialogDescription>
          It closes, and the applicant&apos;s link stops working.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <RemarkField
          id="dealer-app-withdraw-remark"
          label="Why"
          value={remark}
          error={shown ? (problem ?? undefined) : undefined}
          onChange={setRemark}
        />
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={withdraw.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={withdraw.state}
          loadingLabel="Withdrawing…"
          successLabel="Withdrawn"
          errorLabel="Not withdrawn"
        >
          Withdraw
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * Approve (under a distributor, or directly under Polysil, with a code or the next one),
 * return to the applicant, or reject. A remark is needed to return or reject.
 */
function DecideForm({
  application,
  onClose,
}: {
  application: DealerApplication;
  onClose: () => void;
}): React.JSX.Element {
  const mutation = useDecideDealerApplication();
  const idempotency = useIdempotencyKey();
  const [decision, setDecision] = useState<Decision>("approve");
  const [remark, setRemark] = useState("");
  const [parent, setParent] = useState<ParentChoice | null>(null);
  const [code, setCode] = useState("");
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<Readonly<Record<string, string>>>({});
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const remarkProblem =
    decision !== "approve" && remark.trim() === ""
      ? decision === "return"
        ? "Say what the applicant should fix."
        : "Say why it is rejected."
      : null;
  const shownRemark = (shown ? remarkProblem : null) ?? server.remark;

  const decide = useAsyncAction({
    action: () => {
      const body = {
        decision,
        remark: remark.trim() === "" ? null : remark.trim(),
        parent_id: decision === "approve" ? (parent?.id ?? null) : null,
        code: decision === "approve" && code.trim() !== "" ? code.trim().toUpperCase() : null,
      };
      return mutation.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleDecideDealerApplication",
    dataId: "CHNL-007",
    onSuccess: (decided) => {
      idempotency.reset();
      toast.success(
        decided.status === "approved"
          ? "Approved: the dealer is added"
          : decided.status === "returned"
            ? "Returned to the applicant"
            : "Rejected",
      );
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null && (fields.remark !== undefined || fields.parent_id !== undefined)) {
        setServer(fields);
        return;
      }
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next.title, { description: next.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });

  return (
    <form
      noValidate
      aria-label="Decide the application"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer({});
        setRefusal(null);
        if (remarkProblem !== null) return;
        void decide.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Decide {application.firmName}&apos;s application</DialogTitle>
        <DialogDescription>
          Approving adds the dealer and a login on {application.contactName}&apos;s mobile.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field>
          <FieldLabel id="dealer-app-decision-label">Decision</FieldLabel>
          <RadioGroup<Decision>
            aria-labelledby="dealer-app-decision-label"
            value={decision}
            onValueChange={(next) => {
              setDecision(next);
              setServer({});
            }}
            className="gap-2"
          >
            {DECISIONS.map((item) => (
              <label key={item} className="flex items-center gap-2 text-sm text-foreground">
                <RadioGroupItem value={item} />
                {DECISION_LABELS[item]}
              </label>
            ))}
          </RadioGroup>
        </Field>
        {decision === "approve" ? (
          <>
            <Field data-invalid={server.parent_id === undefined ? undefined : true}>
              <FieldLabel htmlFor="dealer-app-parent">
                Under a distributor
                <span className="font-normal text-muted-foreground">(optional)</span>
              </FieldLabel>
              <ParentPicker
                id="dealer-app-parent"
                type="distributor"
                value={parent}
                onValueChange={setParent}
                aria-invalid={server.parent_id === undefined ? undefined : true}
                aria-describedby={
                  server.parent_id === undefined
                    ? "dealer-app-parent-hint"
                    : "dealer-app-parent-error"
                }
              />
              {server.parent_id === undefined ? (
                <FieldDescription id="dealer-app-parent-hint">
                  Empty: directly under Polysil.
                </FieldDescription>
              ) : null}
              <FieldError id="dealer-app-parent-error">
                {server.parent_id === undefined ? undefined : "Choose an active distributor."}
              </FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="dealer-app-code">
                Partner code
                <span className="font-normal text-muted-foreground">(optional)</span>
              </FieldLabel>
              <Input
                id="dealer-app-code"
                value={code}
                autoComplete="off"
                className="font-mono"
                aria-describedby="dealer-app-code-hint"
                onChange={(event) => {
                  setCode(event.target.value);
                }}
              />
              <FieldDescription id="dealer-app-code-hint">
                Empty: the next one, like DLR-GJ-0012.
              </FieldDescription>
            </Field>
          </>
        ) : null}
        <RemarkField
          id="dealer-app-decision-remark"
          label={decision === "approve" ? "Remark" : decision === "return" ? "What to fix" : "Why"}
          optional={decision === "approve"}
          value={remark}
          error={shownRemark}
          onChange={setRemark}
        />
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={decide.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant={decision === "reject" ? "destructive" : "primary"}
          state={decide.state}
          loadingLabel="Saving…"
          successLabel="Done"
          errorLabel="Not saved"
        >
          {DECISION_LABELS[decision]}
        </Button>
      </DialogFooter>
    </form>
  );
}

function RemarkField({
  id,
  label,
  optional = false,
  value,
  error,
  onChange,
}: {
  id: string;
  label: string;
  optional?: boolean;
  value: string;
  error: string | undefined;
  onChange: (next: string) => void;
}): React.JSX.Element {
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      <Textarea
        id={id}
        rows={3}
        maxLength={500}
        value={value}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={error === undefined ? undefined : `${id}-error`}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}
