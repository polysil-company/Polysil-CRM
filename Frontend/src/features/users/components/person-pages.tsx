"use client";

import { ArrowLeft01Icon, LockIcon, Tick02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound, useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { useCreateUser, usePatchUser } from "@/features/users/api/users.mutations";
import { userDetailQueryOptions } from "@/features/users/api/users.queries";
import type { UserDetail } from "@/features/users/api/users.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import { PasswordOnce } from "./person-dialogs";
import {
  createRequestOf,
  draftOf,
  draftProblems,
  emptyDraft,
  formFieldsOf,
  patchRequestOf,
  PersonFields,
  type PersonDraft,
  type PersonField,
} from "./person-form";

const log = createLogger({
  file: "features/users/components/person-pages.tsx",
  dataId: "ADMN-003",
});

function BackLink({
  href,
  label,
}: {
  href: "/users" | `/users/${string}`;
  label: string;
}): React.JSX.Element {
  return (
    <Link
      href={href}
      className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "self-start")}
    >
      <Icon icon={ArrowLeft01Icon} />
      {label}
    </Link>
  );
}

function FormAlert({ text }: { text: string | undefined }): React.JSX.Element | null {
  return text === undefined ? null : (
    <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
      {text}
    </p>
  );
}

/** A refusal as the form shows it: fields on their inputs, anything else above the buttons. */
function errorsOf(error: unknown): Partial<Record<PersonField, string>> {
  const fields = readFieldErrors(error);
  if (fields !== null) return formFieldsOf(fields);
  if (isApiError(error) && error.status === 403) return { form: "You may not do this." };
  return { form: toUserFacingError(error).title };
}

/**
 * ADMN-003 · Add a person. Once added, a staff member's temporary password is shown once, to
 * pass on in person or by phone; then their page, or another person.
 */
export function NewPerson(): React.JSX.Element {
  const canCreate = useCan("users", "create");
  const session = useSession();
  const router = useRouter();
  const create = useCreateUser();
  const idempotency = useIdempotencyKey();
  const [draft, setDraft] = useState<PersonDraft>(emptyDraft);
  const [shown, setShown] = useState(false);
  const [serverErrors, setServerErrors] = useState<Partial<Record<PersonField, string>>>({});
  const [created, setCreated] = useState<{ user: UserDetail; password: string | null } | null>(
    null,
  );
  const problems = draftProblems(draft, "create");
  const errors = { ...serverErrors, ...(shown ? problems : {}) };

  const submit = useAsyncAction({
    action: () => {
      const body = createRequestOf(draft);
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleCreatePerson",
    dataId: "ADMN-003",
    onSuccess: (user) => {
      idempotency.reset();
      toast.success(`${user.name} added`);
      setCreated({ user, password: user.userType === "staff" ? draft.password : null });
    },
    onError: (error) => {
      setServerErrors(errorsOf(error));
    },
  });

  if (session.data !== undefined && !canCreate) {
    return (
      <EmptyState
        icon={LockIcon}
        title="You can't add people"
        description="Ask an administrator to add them."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }

  if (created !== null) {
    return (
      <section aria-label="Person added" className="mx-auto flex w-full max-w-2xl flex-col gap-4">
        <div className="flex items-center gap-2 text-success">
          <Icon icon={Tick02Icon} />
          <h1 className="text-lg font-semibold text-foreground">{created.user.name} is added</h1>
        </div>
        {created.password === null ? (
          <p className="text-sm text-muted-foreground">
            They sign in with a code sent on WhatsApp to their mobile.
          </p>
        ) : (
          <PasswordOnce password={created.password} name={created.user.name} />
        )}
        <div className="flex flex-wrap gap-2">
          <Link href={`/users/${created.user.id}`} className={buttonVariants()}>
            Open their page
          </Link>
          <Button
            variant="outline"
            onClick={() => {
              setCreated(null);
              setDraft(emptyDraft());
              setShown(false);
              setServerErrors({});
            }}
          >
            Add another person
          </Button>
        </div>
      </section>
    );
  }

  return (
    <form
      noValidate
      aria-label="New person"
      className="mx-auto flex w-full max-w-3xl flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServerErrors({});
        if (Object.keys(problems).length > 0) return;
        void submit.run();
      }}
    >
      <BackLink href="/users" label="Users & roles" />
      <h1 className="text-xl font-semibold text-foreground">New person</h1>
      <PersonFields
        mode="create"
        draft={draft}
        errors={errors}
        onChange={(next) => {
          setDraft(next);
          setServerErrors({});
        }}
      />
      <FormAlert text={errors.form} />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          disabled={submit.isBusy}
          onClick={() => {
            router.push("/users");
          }}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Adding…"
          successLabel="Added"
          errorLabel="Not added"
        >
          Add the person
        </Button>
      </div>
    </form>
  );
}

/** ADMN-004 · Correct a person: only what changed is sent. */
export function EditPerson({ userId }: { userId: string }): React.JSX.Element {
  const query = useQuery(userDetailQueryOptions(userId));
  if (query.status === "pending") {
    return (
      <div role="status" aria-label="Loading the person" className="flex flex-col gap-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 404) notFound();
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <EditPersonForm user={query.data} />;
}

function EditPersonForm({ user }: { user: UserDetail }): React.JSX.Element {
  const router = useRouter();
  const session = useSession();
  const canEdit = useCan("users", "edit");
  const patch = usePatchUser();
  const idempotency = useIdempotencyKey();
  const [draft, setDraft] = useState<PersonDraft>(() => draftOf(user));
  const [shown, setShown] = useState(false);
  const [serverErrors, setServerErrors] = useState<Partial<Record<PersonField, string>>>({});
  const isSelf = session.data?.user.id === user.id;
  const problems = draftProblems(draft, "edit");
  const errors = { ...serverErrors, ...(shown ? problems : {}) };
  const body = patchRequestOf(draft, user, isSelf);
  const nothing = Object.keys(body).length === 0;

  const submit = useAsyncAction({
    action: () =>
      patch.mutateAsync({ userId: user.id, body, idempotencyKey: idempotency.keyFor(body) }),
    logger: log,
    fn: "handleEditPerson",
    dataId: "ADMN-004",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`${user.name} saved`);
      router.push(`/users/${user.id}`);
    },
    onError: (error) => {
      setServerErrors(errorsOf(error));
    },
  });

  if (session.data !== undefined && !canEdit) {
    return (
      <EmptyState
        icon={LockIcon}
        title="You can't change people"
        description="Ask an administrator to make the change."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }

  return (
    <form
      noValidate
      aria-label={`Edit ${user.name}`}
      className="mx-auto flex w-full max-w-3xl flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServerErrors({});
        if (Object.keys(problems).length > 0 || nothing) return;
        void submit.run();
      }}
    >
      <BackLink href={`/users/${user.id}`} label={user.name} />
      <h1 className="text-xl font-semibold text-foreground">Edit {user.name}</h1>
      <PersonFields
        mode="edit"
        draft={draft}
        errors={errors}
        isSelf={isSelf}
        onChange={(next) => {
          setDraft(next);
          setServerErrors({});
        }}
      />
      <FormAlert text={errors.form} />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
        {nothing ? (
          <p aria-live="polite" className="text-xs text-muted-foreground sm:mr-auto">
            Nothing changed yet.
          </p>
        ) : null}
        <Button
          type="button"
          variant="outline"
          disabled={submit.isBusy}
          onClick={() => {
            router.push(`/users/${user.id}`);
          }}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={nothing}
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save changes
        </Button>
      </div>
    </form>
  );
}
