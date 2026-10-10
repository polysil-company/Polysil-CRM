"use client";

import { Copy01Icon, RefreshIcon, Tick02Icon } from "@hugeicons/core-free-icons";
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
import { leadAssigneesQueryOptions } from "@/features/leads/api/leads.queries";
import { useHandOver, useSetTemporaryPassword } from "@/features/users/api/users.mutations";
import type { HandoverResult, UserDetail } from "@/features/users/api/users.schemas";
import { generateTemporaryPassword } from "@/features/users/lib/temporary-password";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/users/components/person-dialogs.tsx",
  dataId: "ADMN-005",
});

/** The backend's answer in words: a field's reason, else what went wrong. */
export function refusalOf(error: unknown): string {
  const fields = readFieldErrors(error);
  if (fields !== null) {
    const first = Object.values(fields)[0];
    if (first !== undefined) return `${first.charAt(0).toUpperCase()}${first.slice(1)}.`;
  }
  if (isApiError(error) && error.status === 403) return "You may not do this.";
  return toUserFacingError(error).title;
}

function RefusalAlert({ text }: { text: string | null }): React.JSX.Element | null {
  return text === null ? null : (
    <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
      {text}
    </p>
  );
}

/** The temporary password, shown once with a copy button: it is never shown again. */
export function PasswordOnce({
  password,
  name,
}: {
  password: string;
  name: string;
}): React.JSX.Element {
  const { copied, copy } = useCopyToClipboard();
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-warning/40 bg-warning-soft p-3 sm:p-4">
      <p className="text-sm font-medium text-foreground">Give {name} this temporary password</p>
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded-md bg-card px-2.5 py-1.5 font-mono text-base tracking-wide text-foreground select-all">
          {password}
        </code>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            void copy(password).then((done) => {
              if (!done) toast.error("Couldn't copy: select the password and copy it yourself.");
            });
          }}
        >
          <Icon icon={copied ? Tick02Icon : Copy01Icon} />
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Tell them in person or by phone, not in writing. It is shown only now; they choose their own
        when they first sign in.
      </p>
    </div>
  );
}

/**
 * ADMN-005 · A new temporary password for a staff member: suggested, or typed. Every session of
 * theirs ends, and they must change it at the next sign-in.
 */
export function TemporaryPasswordDialog({
  user,
  onClose,
}: {
  user: UserDetail;
  onClose: () => void;
}): React.JSX.Element {
  const mutation = useSetTemporaryPassword();
  const idempotency = useIdempotencyKey();
  const [password, setPassword] = useState(generateTemporaryPassword);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [done, setDone] = useState<{ password: string; revoked: number } | null>(null);
  const problem = password.length < 12 ? "At least 12 characters." : null;
  const submit = useAsyncAction({
    action: () => {
      const body = { password };
      return mutation.mutateAsync({
        userId: user.id,
        password,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleSetTemporaryPassword",
    dataId: "ADMN-005",
    onSuccess: (result) => {
      idempotency.reset();
      setDone({ password, revoked: result.sessionsRevoked });
    },
    onError: (error) => {
      setRefusal(refusalOf(error));
    },
  });

  if (done !== null) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <DialogHeader>
          <DialogTitle>New temporary password set</DialogTitle>
          <DialogDescription>
            {done.revoked === 0
              ? `${user.name} had no live sessions.`
              : `${user.name} was signed out of ${String(done.revoked)} session${done.revoked === 1 ? "" : "s"}.`}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <PasswordOnce password={done.password} name={user.name} />
        </DialogBody>
        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </div>
    );
  }

  const error = shown ? problem : null;
  return (
    <form
      noValidate
      aria-label="Set a temporary password"
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
        <DialogTitle>Set a temporary password</DialogTitle>
        <DialogDescription>
          {user.name} is signed out everywhere and must choose their own password at the next
          sign-in.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        <Field data-invalid={error === null ? undefined : true}>
          <FieldLabel htmlFor="temporary-password">Temporary password</FieldLabel>
          <div className="flex gap-2">
            <Input
              id="temporary-password"
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
              value={password}
              aria-invalid={error === null ? undefined : true}
              aria-describedby={
                error === null ? "temporary-password-help" : "temporary-password-error"
              }
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
            <Button
              type="button"
              variant="outline"
              aria-label="Suggest another password"
              onClick={() => {
                setPassword(generateTemporaryPassword());
              }}
            >
              <Icon icon={RefreshIcon} />
            </Button>
          </div>
          {error === null ? (
            <FieldDescription id="temporary-password-help">
              Suggested for you; at least 12 characters. You&apos;ll see it again after saving.
            </FieldDescription>
          ) : null}
          <FieldError id="temporary-password-error">{error}</FieldError>
        </Field>
        <RefusalAlert text={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Setting…"
          successLabel="Set"
          errorLabel="Not set"
        >
          Set the password
        </Button>
      </DialogFooter>
    </form>
  );
}

/** A yes-or-no action with what it does in words: sign out everywhere, unlock, delete… */
export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  destructive = false,
  action,
  fn,
  dataId,
  onDone,
}: {
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  action: (idempotencyKey: string) => Promise<unknown>;
  fn: string;
  dataId: "ADMN-004" | "ADMN-005" | "ADMN-006";
  onDone: () => void;
}): React.JSX.Element {
  const [key] = useState(createRequestId);
  const [refusal, setRefusal] = useState<string | null>(null);
  const submit = useAsyncAction({
    action: () => action(key),
    logger: log,
    fn,
    dataId,
    onSuccess: onDone,
    onError: (error) => {
      setRefusal(refusalOf(error));
    },
  });
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <DialogBody>
        <RefusalAlert text={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep as is
        </DialogClose>
        <Button
          variant={destructive ? "destructive" : "primary"}
          state={submit.state}
          loadingLabel="Working…"
          successLabel="Done"
          errorLabel="Not done"
          onClick={() => {
            setRefusal(null);
            void submit.run();
          }}
        >
          {confirmLabel}
        </Button>
      </DialogFooter>
    </div>
  );
}

/**
 * ADMN-006 · Hand a leaver's open leads, and every open task, to someone who can work them.
 * One call moves at most 500 leads; the dialog repeats with a new key while any remain, then
 * deactivates the leaver if asked. Nobody hands over to themselves, and the caller never
 * deactivates their own row.
 */
export function HandoverDialog({
  user,
  isSelf,
  onClose,
}: {
  user: UserDetail;
  isSelf: boolean;
  onClose: () => void;
}): React.JSX.Element {
  const mutation = useHandOver();
  const assignees = useQuery(leadAssigneesQueryOptions());
  const [target, setTarget] = useState<string | null>(null);
  const [deactivate, setDeactivate] = useState(false);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [progress, setProgress] = useState<HandoverResult | null>(null);
  const [finished, setFinished] = useState<{ leads: number; tasks: number; off: boolean } | null>(
    null,
  );
  const people = (assignees.data ?? []).filter((person) => person.id !== user.id);
  const items = people.map((person) => ({ value: person.id, label: person.name }));
  const targetName = people.find((person) => person.id === target)?.name ?? "them";

  const submit = useAsyncAction({
    action: async () => {
      let leads = 0;
      let tasks = 0;
      let off = false;
      // Each batch is a new request, so each gets its own key (a replay would move nothing).
      for (;;) {
        const result = await mutation.mutateAsync({
          userId: user.id,
          body: { to_user_id: target ?? "", deactivate: false },
          idempotencyKey: createRequestId(),
        });
        leads += result.leadsMoved;
        tasks += result.tasksMoved;
        setProgress(result);
        if (result.remaining === 0) break;
      }
      if (deactivate) {
        const result = await mutation.mutateAsync({
          userId: user.id,
          body: { to_user_id: target ?? "", deactivate: true },
          idempotencyKey: createRequestId(),
        });
        tasks += result.tasksMoved;
        off = result.deactivated;
      }
      return { leads, tasks, off };
    },
    logger: log,
    fn: "handleHandover",
    dataId: "ADMN-006",
    onSuccess: (result) => {
      setFinished(result);
    },
    onError: (error) => {
      setRefusal(refusalOf(error));
    },
  });

  if (finished !== null) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <DialogHeader>
          <DialogTitle>Handed over</DialogTitle>
          <DialogDescription>
            {`${String(finished.leads)} open lead${finished.leads === 1 ? "" : "s"} and ${String(finished.tasks)} open task${finished.tasks === 1 ? "" : "s"} now belong to ${targetName}.`}
            {finished.off ? ` ${user.name} is deactivated and signed out everywhere.` : ""}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </div>
    );
  }

  const error = shown && target === null ? "Choose who takes them over." : null;
  return (
    <form
      noValidate
      aria-label="Hand over"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (target === null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Hand over {user.name}&apos;s work</DialogTitle>
        <DialogDescription>
          {user.openLeads === null || user.openLeads === 0
            ? "No open leads; their open tasks move too."
            : `${String(user.openLeads)} open lead${user.openLeads === 1 ? "" : "s"} and every open task move to the person you choose.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={error === null ? undefined : true}>
          <FieldLabel htmlFor="handover-target">Hand over to</FieldLabel>
          <Select
            items={items}
            value={target}
            onValueChange={(next) => {
              setTarget(typeof next === "string" ? next : null);
            }}
          >
            <SelectTrigger
              id="handover-target"
              className="w-full"
              aria-invalid={error === null ? undefined : true}
              aria-describedby={error === null ? undefined : "handover-target-error"}
            >
              <SelectValue
                placeholder={assignees.isPending ? "Loading people…" : "Choose a person"}
              />
            </SelectTrigger>
            <SelectContent>
              {items.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldDescription>People who can work leads in your scope.</FieldDescription>
          <FieldError id="handover-target-error">{error}</FieldError>
        </Field>
        {isSelf ? null : (
          <div className="flex items-start gap-2">
            <Checkbox
              id="handover-deactivate"
              checked={deactivate}
              onCheckedChange={(checked) => {
                setDeactivate(checked);
              }}
            />
            <Label htmlFor="handover-deactivate" className="flex flex-col items-start gap-0.5">
              <span className="text-sm">Then deactivate {user.name}</span>
              <span className="text-xs font-normal text-muted-foreground">
                For a leaver&apos;s last day: they&apos;re signed out everywhere.
              </span>
            </Label>
          </div>
        )}
        {submit.isBusy && progress !== null && progress.remaining > 0 ? (
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {`Moved ${String(progress.leadsMoved)}; ${String(progress.remaining)} still to go…`}
          </p>
        ) : null}
        <RefusalAlert text={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Handing over…"
          successLabel="Handed over"
          errorLabel="Not handed over"
        >
          Hand over
        </Button>
      </DialogFooter>
    </form>
  );
}
