"use client";

import { ArrowLeft01Icon, LockIcon } from "@hugeicons/core-free-icons";
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
import { useCreatePartner, usePatchPartner } from "@/features/partners/api/partners.mutations";
import { partnerDetailQueryOptions } from "@/features/partners/api/partners.queries";
import type { Partner } from "@/features/partners/api/partners.schemas";
import { childTypeOf } from "@/features/partners/lib/partner-labels";
import { useCan, useIsStaff, useSession } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import {
  createPartnerRequestOf,
  draftOfPartner,
  emptyPartnerDraft,
  partnerDraftProblems,
  partnerFieldsOf,
  patchPartnerRequestOf,
  PartnerFields,
  type PartnerDraft,
  type PartnerField,
} from "./partner-form";

const log = createLogger({
  file: "features/partners/components/partner-pages.tsx",
  dataId: "CHNL-002",
});

function BackLink({
  href,
  label,
}: {
  href: "/partners" | `/partners/${string}`;
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
function errorsOf(error: unknown): Partial<Record<PartnerField, string>> {
  const fields = readFieldErrors(error);
  if (fields !== null) return partnerFieldsOf(fields);
  if (isApiError(error) && error.status === 403) return { form: "You may not do this." };
  if (isApiError(error) && error.status === 404) {
    return { form: "The partner it goes under is no longer in your area. Choose again." };
  }
  return { form: toUserFacingError(error).title };
}

function FormSkeleton({ label }: { label: string }): React.JSX.Element {
  return (
    <div role="status" aria-label={label} className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-40 w-full rounded-xl" />
      <Skeleton className="h-56 w-full rounded-xl" />
    </div>
  );
}

/**
 * CHNL-002 · Add a partner. From a partner's page, `parentId` starts the form as the next
 * type down under it ("Add a dealer"); otherwise as a distributor.
 */
export function NewPartner({
  parentId: askedParentId,
}: {
  parentId: string | null;
}): React.JSX.Element {
  const canCreate = useCan("partners", "create");
  const session = useSession();
  const staff = useIsStaff();
  // CHNL-002 · A distributor or dealer adds the next type down under itself, whatever the URL says.
  const parentId = staff ? askedParentId : (session.data?.partner?.id ?? null);
  const parent = useQuery({
    ...partnerDetailQueryOptions(parentId ?? ""),
    enabled: parentId !== null,
  });

  if (session.data !== undefined && !canCreate) {
    return (
      <EmptyState
        icon={LockIcon}
        title="You can't add partners"
        description="Ask an administrator or your manager to add them."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }
  if (parentId === null) {
    // A partner user always has its own partner; without one there is nothing to add under.
    return staff ? (
      <NewPartnerForm initial={emptyPartnerDraft()} />
    ) : (
      <FormSkeleton label="Loading your account" />
    );
  }
  if (parent.status === "pending") return <FormSkeleton label="Loading the partner above" />;
  if (parent.status === "error") {
    if (isApiError(parent.error) && parent.error.status === 404) notFound();
    return (
      <ErrorState
        error={parent.error}
        onRetry={() => {
          void parent.refetch();
        }}
      />
    );
  }
  const childType = childTypeOf(parent.data.type);
  return (
    <NewPartnerForm
      initial={
        childType === null
          ? emptyPartnerDraft()
          : {
              ...emptyPartnerDraft(childType),
              parent: { id: parent.data.id, name: parent.data.name },
              territory: parent.data.territory,
            }
      }
      backTo={staff ? parent.data : undefined}
    />
  );
}

function NewPartnerForm({
  initial,
  backTo,
}: {
  initial: PartnerDraft;
  backTo?: Partner | undefined;
}): React.JSX.Element {
  const router = useRouter();
  const staff = useIsStaff();
  const create = useCreatePartner();
  const idempotency = useIdempotencyKey();
  const [draft, setDraft] = useState<PartnerDraft>(initial);
  const [shown, setShown] = useState(false);
  const [serverErrors, setServerErrors] = useState<Partial<Record<PartnerField, string>>>({});
  const problems = partnerDraftProblems(draft, "create");
  const errors = { ...serverErrors, ...(shown ? problems : {}) };
  const back: "/partners" | `/partners/${string}` =
    backTo === undefined ? "/partners" : `/partners/${backTo.id}`;

  const submit = useAsyncAction({
    action: () => {
      const body = createPartnerRequestOf(draft, staff);
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleCreatePartner",
    dataId: "CHNL-002",
    onSuccess: (partner) => {
      idempotency.reset();
      toast.success(`${partner.name} added`);
      router.push(`/partners/${partner.id}`);
    },
    onError: (error) => {
      setServerErrors(errorsOf(error));
    },
  });

  return (
    <form
      noValidate
      aria-label="New partner"
      className="mx-auto flex w-full max-w-3xl flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServerErrors({});
        if (Object.keys(problems).length > 0) return;
        void submit.run();
      }}
    >
      <BackLink href={back} label={backTo?.name ?? "Channel partners"} />
      <h1 className="text-xl font-semibold text-foreground">New partner</h1>
      <PartnerFields
        mode="create"
        draft={draft}
        errors={errors}
        staff={staff}
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
            router.push(back);
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
          Add the partner
        </Button>
      </div>
    </form>
  );
}

/** CHNL-003 · Correct a partner: only what changed is sent. */
export function EditPartner({ partnerId }: { partnerId: string }): React.JSX.Element {
  const query = useQuery(partnerDetailQueryOptions(partnerId));
  if (query.status === "pending") return <FormSkeleton label="Loading the partner" />;
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
  return <EditPartnerForm partner={query.data} />;
}

function EditPartnerForm({ partner }: { partner: Partner }): React.JSX.Element {
  const router = useRouter();
  const session = useSession();
  const canEdit = useCan("partners", "edit");
  const staff = useIsStaff();
  const patch = usePatchPartner();
  const idempotency = useIdempotencyKey();
  const [draft, setDraft] = useState<PartnerDraft>(() => draftOfPartner(partner));
  const [shown, setShown] = useState(false);
  const [serverErrors, setServerErrors] = useState<Partial<Record<PartnerField, string>>>({});
  const problems = partnerDraftProblems(draft, "edit");
  const errors = { ...serverErrors, ...(shown ? problems : {}) };
  const body = patchPartnerRequestOf(draft, partner, staff);
  const nothing = Object.keys(body).length === 0;

  const submit = useAsyncAction({
    action: () =>
      patch.mutateAsync({ partnerId: partner.id, body, idempotencyKey: idempotency.keyFor(body) }),
    logger: log,
    fn: "handleEditPartner",
    dataId: "CHNL-003",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`${partner.name} saved`);
      router.push(`/partners/${partner.id}`);
    },
    onError: (error) => {
      setServerErrors(errorsOf(error));
    },
  });

  if (session.data !== undefined && !canEdit) {
    return (
      <EmptyState
        icon={LockIcon}
        title="You can't change partners"
        description="Ask an administrator or your manager to make the change."
        className="rounded-xl border border-dashed border-border"
      />
    );
  }

  return (
    <form
      noValidate
      aria-label={`Edit ${partner.name}`}
      className="mx-auto flex w-full max-w-3xl flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServerErrors({});
        if (Object.keys(problems).length > 0 || nothing) return;
        void submit.run();
      }}
    >
      <BackLink href={`/partners/${partner.id}`} label={partner.name} />
      <h1 className="text-xl font-semibold text-foreground">Edit {partner.name}</h1>
      <PartnerFields
        mode="edit"
        draft={draft}
        errors={errors}
        staff={staff}
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
            router.push(`/partners/${partner.id}`);
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
