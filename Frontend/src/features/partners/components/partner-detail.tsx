"use client";

import {
  Add01Icon,
  ArrowLeft01Icon,
  Edit02Icon,
  Store01Icon,
  StoreRemove01Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useSetPartnerOpen } from "@/features/partners/api/partners.mutations";
import { partnerDetailQueryOptions } from "@/features/partners/api/partners.queries";
import type { Partner } from "@/features/partners/api/partners.schemas";
import {
  childTypeOf,
  PARTNER_TYPE_LABELS,
  PARTNER_TYPE_PLURALS,
} from "@/features/partners/lib/partner-labels";
import { PartnerCreditCard } from "@/features/payments/components/partner-credit";
import { PartnerLedgerCard } from "@/features/payments/components/partner-ledger";
import { DealerRatingCard } from "@/features/ratings/components/dealer-rating";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { refusalOf } from "@/features/users/components/person-dialogs";
import { mobileText } from "@/features/users/lib/user-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { formatDateTime, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/partners/components/partner-detail.tsx",
  dataId: "CHNL-001",
});

/**
 * CHNL-001 · One channel partner: where it sits (its type, the partner above it and its
 * territory), its business and contact details, its credit terms for staff, and its users.
 * Whoever may edit partners corrects it; staff close or reopen it (CHNL-004), and whoever
 * may add partners adds the next type down under it.
 */
export function PartnerDetail({ partnerId }: { partnerId: string }): React.JSX.Element {
  const query = useQuery(partnerDetailQueryOptions(partnerId));

  if (query.status === "pending") return <PartnerDetailSkeleton />;
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
  return <PartnerView partner={query.data} />;
}

function Item({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}

function Missing({ text }: { text: string }): React.JSX.Element {
  return <span className="text-subtle-foreground">{text}</span>;
}

function PartnerView({ partner }: { partner: Partner }): React.JSX.Element {
  const canEdit = useCan("partners", "edit");
  const canCreate = useCan("partners", "create");
  const staff = useIsStaff();
  const [confirming, setConfirming] = useState(false);
  const type = PARTNER_TYPE_LABELS[partner.type];
  const childType = childTypeOf(partner.type);

  return (
    <article aria-label={partner.name} className="flex flex-col gap-4">
      <Link
        href="/partners"
        className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "self-start")}
      >
        <Icon icon={ArrowLeft01Icon} />
        Channel partners
      </Link>

      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-xl font-semibold text-foreground">{partner.name}</h1>
          <p className="text-sm text-muted-foreground">
            {partner.code} · {type}
            {partner.parent === null ? "" : ` under ${partner.parent.name}`}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="neutral">{type}</Badge>
            {partner.active ? (
              <Badge variant="success" dot>
                Open
              </Badge>
            ) : (
              <Badge variant="neutral" dot>
                Closed
              </Badge>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {canEdit && partner.active ? (
            <Link
              href={`/partners/${partner.id}/edit`}
              className={buttonVariants({ variant: "outline" })}
            >
              <Icon icon={Edit02Icon} />
              Edit
            </Link>
          ) : null}
          {canEdit && staff ? (
            <Button
              variant="outline"
              onClick={() => {
                setConfirming(true);
              }}
            >
              <Icon icon={partner.active ? StoreRemove01Icon : Store01Icon} />
              {partner.active ? "Close" : "Reopen"}
            </Button>
          ) : null}
          {canCreate && childType !== null && partner.active ? (
            <Link
              href={`/partners/new?parent=${encodeURIComponent(partner.id)}`}
              className={buttonVariants()}
            >
              <Icon icon={Add01Icon} />
              Add a {PARTNER_TYPE_LABELS[childType].toLowerCase()}
            </Link>
          ) : null}
        </div>
      </header>

      {partner.active ? null : (
        <p role="note" className="rounded-xl border border-border bg-muted p-3 text-sm">
          Closed: its users can&apos;t sign in, and it isn&apos;t offered for new leads. Reopen it
          to correct its details.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle level={2}>Where it sits</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <Item label="Type and price tier">{type}</Item>
              <Item label="Under">
                {partner.parent === null ? (
                  <Missing text="Nobody: a distributor sits at the top" />
                ) : (
                  <Link
                    href={`/partners/${partner.parent.id}`}
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    {partner.parent.name}
                  </Link>
                )}
              </Item>
              <Item label="Territory">{partner.territory?.name ?? <Missing text="Not set" />}</Item>
              {childType === null ? null : (
                <Item label={`Its ${PARTNER_TYPE_PLURALS[childType]}`}>
                  <Link
                    href={`/partners?parent=${encodeURIComponent(partner.id)}&status=all`}
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    See the {PARTNER_TYPE_PLURALS[childType]} under it
                  </Link>
                </Item>
              )}
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle level={2}>Business</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <Item label="GSTIN">
                {partner.gstin === null ? (
                  <Missing text="Not recorded" />
                ) : (
                  <span className="font-mono">{partner.gstin}</span>
                )}
              </Item>
              <Item label="Registered for GST">{partner.gstRegistered ? "Yes" : "No"}</Item>
              <Item label="PAN">
                {partner.pan === null ? (
                  <Missing text="Not recorded" />
                ) : (
                  <span className="font-mono">{partner.pan}</span>
                )}
              </Item>
              <Item label="Users">
                {partner.users === 0
                  ? "No one signs in for it yet"
                  : `${String(partner.users)} active user${partner.users === 1 ? "" : "s"}`}
              </Item>
              <Item label="Added">{formatDateTime(partner.createdAt)}</Item>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle level={2}>Contact</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <Item label="Contact person">
                {partner.contactName ?? <Missing text="Not recorded" />}
              </Item>
              <Item label="Mobile">
                {mobileText(partner.mobile) ?? <Missing text="Not recorded" />}
              </Item>
              <Item label="Email">{partner.email ?? <Missing text="Not recorded" />}</Item>
              <Item label="Address" className="sm:col-span-2">
                {partner.address === null ? (
                  <Missing text="Not recorded" />
                ) : (
                  <span className="whitespace-pre-line">{partner.address}</span>
                )}
              </Item>
            </dl>
          </CardContent>
        </Card>

        {staff ? (
          <Card>
            <CardHeader>
              <CardTitle level={2}>Credit terms</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-4 sm:grid-cols-2">
                <Item label="Credit limit">
                  {partner.creditLimit === null ? (
                    <Missing text="Not set" />
                  ) : (
                    formatInr(partner.creditLimit)
                  )}
                </Item>
                <Item label="Payment terms">
                  {partner.paymentTermsDays === null ? (
                    <Missing text="Not set" />
                  ) : (
                    `${String(partner.paymentTermsDays)} day${partner.paymentTermsDays === 1 ? "" : "s"}`
                  )}
                </Item>
              </dl>
            </CardContent>
          </Card>
        ) : null}
        {staff ? <PartnerCreditCard partnerId={partner.id} /> : null}
        {staff ? <DealerRatingCard partnerId={partner.id} /> : null}
      </div>

      {staff ? <PartnerLedgerCard partnerId={partner.id} /> : null}

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent size="sm">
          {confirming ? (
            <OpenCloseDialog
              partner={partner}
              onDone={() => {
                setConfirming(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </article>
  );
}

/**
 * CHNL-004 · Close: the partner becomes inactive and every user anchored on it is signed out
 * and deactivated. Reopen: the partner only; its people stay inactive until reactivated one
 * by one from Users & roles.
 */
function OpenCloseDialog({
  partner,
  onDone,
}: {
  partner: Partner;
  onDone: () => void;
}): React.JSX.Element {
  const mutation = useSetPartnerOpen();
  const [key] = useState(createRequestId);
  const [refusal, setRefusal] = useState<string | null>(null);
  const closing = partner.active;
  const submit = useAsyncAction({
    action: () =>
      mutation.mutateAsync({ partnerId: partner.id, open: !closing, idempotencyKey: key }),
    logger: log,
    fn: closing ? "handleClosePartner" : "handleReopenPartner",
    dataId: "CHNL-004",
    onSuccess: (result) => {
      if (closing) {
        toast.success(`${partner.name} is closed`);
      } else {
        toast.success(
          result.usersInactive === 0
            ? `${partner.name} is open again`
            : `${partner.name} is open again. Its ${String(result.usersInactive)} user${result.usersInactive === 1 ? " stays" : "s stay"} deactivated until reactivated in Users & roles.`,
        );
      }
      onDone();
    },
    onError: (error) => {
      setRefusal(refusalOf(error));
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>{closing ? `Close ${partner.name}?` : `Reopen ${partner.name}?`}</DialogTitle>
        <DialogDescription>
          {closing
            ? partner.users === 0
              ? "It stops being offered for new leads and orders. Its records stay."
              : `Its ${String(partner.users)} user${partner.users === 1 ? " is" : "s are"} signed out everywhere and deactivated. It stops being offered for new leads and orders; its records stay.`
            : "It's offered for new leads and orders again. Its users stay deactivated: reactivate each one in Users & roles."}
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
          Keep as is
        </DialogClose>
        <Button
          variant={closing ? "destructive" : "primary"}
          state={submit.state}
          loadingLabel={closing ? "Closing…" : "Reopening…"}
          successLabel="Done"
          errorLabel="Not done"
          onClick={() => {
            setRefusal(null);
            void submit.run();
          }}
        >
          {closing ? "Close the partner" : "Reopen"}
        </Button>
      </DialogFooter>
    </div>
  );
}

export function PartnerDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the partner" className="flex flex-col gap-4">
      <Skeleton className="h-8 w-40" />
      <div className="flex flex-col gap-2">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-44 w-full rounded-xl" />
        <Skeleton className="h-44 w-full rounded-xl" />
        <Skeleton className="h-44 w-full rounded-xl" />
        <Skeleton className="h-44 w-full rounded-xl" />
      </div>
    </div>
  );
}
