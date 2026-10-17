"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteCampaign, usePatchCampaign } from "@/features/campaigns/api/campaigns.mutations";
import { campaignQueryOptions } from "@/features/campaigns/api/campaigns.queries";
import type { Campaign } from "@/features/campaigns/api/campaigns.schemas";
import { CAMPAIGN_TYPE_LABELS, campaignDates } from "@/features/campaigns/lib/campaign-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction, type AsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatCount, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { CampaignForm } from "./campaign-form";

const log = createLogger({
  file: "features/campaigns/components/campaign-dialog.tsx",
  dataId: "MKT-005",
});

type Step = "view" | "edit" | "delete";

/**
 * MKT-005 · One campaign: where and when, its cost, and how it did (its leads, won, lost and open,
 * the sales on them, and cost per lead and per win). Marketing changes it, switches it off (staff
 * then can't pick it; a QR code already linked keeps bringing leads under it), or deletes one
 * nothing names yet.
 */
export function CampaignDialog({
  campaignId,
  onClose,
}: {
  campaignId: string;
  onClose: () => void;
}): React.JSX.Element {
  const query = useQuery(campaignQueryOptions(campaignId));
  const [step, setStep] = useState<Step>("view");

  if (query.status === "pending") {
    return (
      <>
        <DialogHeader>
          <DialogTitle>Campaign</DialogTitle>
          <DialogDescription>Loading…</DialogDescription>
        </DialogHeader>
        <DialogBody aria-busy="true" className="flex flex-col gap-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-24 w-full" />
        </DialogBody>
      </>
    );
  }
  if (query.status === "error") {
    return (
      <>
        <DialogHeader>
          <DialogTitle>Campaign</DialogTitle>
          <DialogDescription>It couldn&apos;t be opened.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        </DialogBody>
      </>
    );
  }
  const campaign = query.data;
  if (step === "edit") {
    return (
      <CampaignForm
        campaign={campaign}
        onClose={() => {
          setStep("view");
        }}
      />
    );
  }
  if (step === "delete") {
    return (
      <DeleteStep
        campaign={campaign}
        onBack={() => {
          setStep("view");
        }}
        onDone={onClose}
      />
    );
  }
  return <CampaignView campaign={campaign} onStep={setStep} />;
}

function CampaignView({
  campaign,
  onStep,
}: {
  campaign: Campaign;
  onStep: (step: Step) => void;
}): React.JSX.Element {
  const canEdit = useCan("campaigns", "edit");
  const canDelete = useCan("campaigns", "delete");
  const toggle = useToggle(campaign);
  const summary = campaign.summary;
  const money = (value: string | null): string => (value === null ? "—" : formatInr(value));
  const figures: readonly { term: string; value: string }[] =
    summary === null
      ? []
      : [
          { term: "Leads", value: formatCount(summary.leads) },
          { term: "Won", value: formatCount(summary.won) },
          { term: "Lost", value: formatCount(summary.lost) },
          { term: "Open", value: formatCount(summary.open) },
          ...(summary.salesValue === null
            ? []
            : [{ term: "Sales", value: money(summary.salesValue) }]),
          ...(campaign.costPlanned === null
            ? []
            : [
                { term: "Cost per lead", value: money(summary.costPerLead) },
                { term: "Cost per win", value: money(summary.costPerWon) },
              ]),
        ];

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex flex-wrap items-center gap-2">
          {campaign.name}
          {campaign.active ? (
            <Badge variant="success" dot>
              Running
            </Badge>
          ) : (
            <Badge variant="neutral" dot>
              Switched off
            </Badge>
          )}
        </DialogTitle>
        <DialogDescription>
          {CAMPAIGN_TYPE_LABELS[campaign.type]}
          {campaign.territory === null ? "" : ` · ${campaign.territory.name}`} ·{" "}
          {campaignDates(campaign.startDate, campaign.endDate)}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {figures.length === 0 ? null : (
          <dl aria-label="How it did" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {figures.map((row) => (
              <div key={row.term} className="flex flex-col gap-0.5 rounded-lg bg-muted p-3">
                <dt className="text-xs text-muted-foreground">{row.term}</dt>
                <dd className="text-sm font-semibold text-foreground tabular-nums">{row.value}</dd>
              </div>
            ))}
          </dl>
        )}
        {campaign.costPlanned === null ? null : (
          <p className="text-sm text-foreground tabular-nums">
            Planned {formatInr(campaign.costPlanned)}
            {campaign.costActual === null
              ? " · actual not entered yet"
              : ` · spent ${formatInr(campaign.costActual)}`}
          </p>
        )}
        {campaign.description === null ? null : (
          <p className="text-sm text-muted-foreground">{campaign.description}</p>
        )}
        {summary !== null && summary.leads > 0 ? (
          <Link
            href={`/leads?campaign=${encodeURIComponent(campaign.id)}`}
            className={buttonVariants({ variant: "outline", size: "sm", className: "self-start" })}
          >
            See its leads
          </Link>
        ) : null}
        {toggle.refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {toggle.refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="ghost" />}>Close</DialogClose>
        {canDelete ? (
          <Button
            variant="outline"
            onClick={() => {
              onStep("delete");
            }}
          >
            Delete
          </Button>
        ) : null}
        {canEdit ? (
          <Button
            variant="outline"
            state={toggle.action.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
            onClick={() => {
              void toggle.action.run();
            }}
          >
            {campaign.active ? "Switch off" : "Switch on"}
          </Button>
        ) : null}
        {canEdit ? (
          <Button
            onClick={() => {
              onStep("edit");
            }}
          >
            Change
          </Button>
        ) : null}
      </DialogFooter>
    </>
  );
}

/** Switch a campaign off or on, with what went wrong if it didn't. */
function useToggle(campaign: Campaign): {
  action: AsyncAction<[], Campaign>;
  refusal: string | null;
} {
  const patch = usePatchCampaign();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<string | null>(null);
  const action = useAsyncAction({
    action: () => {
      setRefusal(null);
      const body = { is_active: !campaign.active };
      return patch.mutateAsync({
        campaignId: campaign.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: campaign.id, ...body }),
      });
    },
    logger: log,
    fn: "handleToggleCampaign",
    dataId: "MKT-005",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(saved.active ? `${saved.name} switched on` : `${saved.name} switched off`, {
        description: saved.active
          ? "Staff can pick it again."
          : "Staff can no longer pick it; linked QR codes keep counting leads under it.",
      });
    },
    onError: (error) => {
      setRefusal(toUserFacingError(error).title);
    },
  });
  return { action, refusal };
}

function DeleteStep({
  campaign,
  onBack,
  onDone,
}: {
  campaign: Campaign;
  onBack: () => void;
  onDone: () => void;
}): React.JSX.Element {
  const remove = useDeleteCampaign();
  const idempotency = useIdempotencyKey();
  const [inUse, setInUse] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const toggle = useToggle(campaign);

  const submit = useAsyncAction({
    action: () =>
      remove.mutateAsync({
        campaignId: campaign.id,
        idempotencyKey: idempotency.keyFor({ id: campaign.id, delete: true }),
      }),
    logger: log,
    fn: "handleDeleteCampaign",
    dataId: "MKT-005",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`${campaign.name} deleted`);
      onDone();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "campaign_in_use") {
        setInUse(true);
        return;
      }
      setRefusal(toUserFacingError(error).title);
    },
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>Delete {campaign.name}?</DialogTitle>
        <DialogDescription>
          Only a campaign no lead or QR code names can be deleted.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        {inUse ? (
          <p role="alert" className="rounded-md bg-warning-soft p-3 text-sm text-foreground">
            Leads or QR codes name this campaign, so it stays.
            {campaign.active
              ? " Switch it off instead: staff can no longer pick it."
              : " It is already switched off."}
          </p>
        ) : null}
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" disabled={submit.isBusy} onClick={onBack}>
          Back
        </Button>
        {inUse && campaign.active ? (
          <Button
            state={toggle.action.state}
            loadingLabel="Saving…"
            successLabel="Switched off"
            errorLabel="Not saved"
            onClick={() => {
              void toggle.action.run().then(onBack);
            }}
          >
            Switch off instead
          </Button>
        ) : null}
        {inUse ? null : (
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
            Delete campaign
          </Button>
        )}
      </DialogFooter>
    </>
  );
}
