"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useRecordCommission } from "@/features/commission/api/commission.mutations";
import {
  commissionPreviewQueryOptions,
  liveCommissionQueryOptions,
} from "@/features/commission/api/commission.queries";
import type { Commission, CommissionPreview } from "@/features/commission/api/commission.schemas";
import { rupees, workOutCommission } from "@/features/commission/lib/commission-labels";
import { useCan } from "@/features/session/hooks/use-session";
import type { Application } from "@/features/subsidy/api/subsidy-applications.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { CommissionActions } from "./commission-decisions";
import {
  CommissionFigures,
  CommissionStatusBadge,
  MoneyField,
  moneyProblem,
} from "./commission-parts";

const log = createLogger({
  file: "features/commission/components/application-commission.tsx",
  dataId: "SUBS-016",
});

const TITLE_ID = "application-commission-title";

/**
 * SUBS-016 · Stage 18 on a subsidy application: once every payment is in, the co-ordinator
 * records the dealer's commission and TOD; Accounts approves and pays (FS-033). Shown on a
 * closed application, or on any that already carries a commission.
 */
export function ApplicationCommission({
  application,
}: {
  application: Application;
}): React.JSX.Element | null {
  const closed = application.status === "full_fp_received";
  const live = useQuery(liveCommissionQueryOptions(application.id));
  const none = isApiError(live.error) && live.error.status === 404;
  const forbidden = isApiError(live.error) && live.error.status === 403;

  if (forbidden) return null;
  if (live.status === "pending") return closed ? <CommissionSkeleton /> : null;
  if (live.status === "error" && !none) {
    return (
      <CommissionCard description="The dealer's commission and TOD, once every payment is in.">
        <ErrorState
          error={live.error}
          onRetry={() => {
            void live.refetch();
          }}
          className="border-0 p-2"
        />
      </CommissionCard>
    );
  }
  if (live.data !== undefined)
    return <RecordedCommission application={application} commission={live.data} />;
  return closed ? <NotYetRecorded application={application} /> : null;
}

function CommissionCard({
  description,
  badge,
  children,
}: {
  description: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section aria-labelledby={TITLE_ID}>
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <CardTitle level={3} id={TITLE_ID}>
              Dealer commission{" "}
              <span className="font-normal text-muted-foreground">· stage 18</span>
            </CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          {badge}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">{children}</CardContent>
      </Card>
    </section>
  );
}

function CommissionSkeleton(): React.JSX.Element {
  return (
    <CommissionCard description="The dealer's commission and TOD, once every payment is in.">
      <div aria-busy="true" aria-label="Loading the commission" className="flex flex-col gap-2">
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-5 w-1/3" />
      </div>
    </CommissionCard>
  );
}

/** Nothing recorded yet: the starting figures, the rate in force, and the form. */
function NotYetRecorded({ application }: { application: Application }): React.JSX.Element | null {
  const canRecord = useCan("subsidy", "edit");
  const canAddRate = useCan("masters", "edit");
  const preview = useQuery(commissionPreviewQueryOptions(application.id));
  const code = isApiError(preview.error) ? preview.error.code : null;

  if (code === "not_closed") return null;
  if (preview.status === "pending") return <CommissionSkeleton />;
  if (code === "no_partner") {
    return (
      <CommissionCard description="The dealer's commission and TOD, once every payment is in.">
        <p className="text-sm text-muted-foreground">
          This application has no dealer, so no commission is due.
        </p>
      </CommissionCard>
    );
  }
  if (preview.status === "error") {
    return (
      <CommissionCard description="The dealer's commission and TOD, once every payment is in.">
        <ErrorState
          error={preview.error}
          onRetry={() => {
            void preview.refetch();
          }}
          className="border-0 p-2"
        />
      </CommissionCard>
    );
  }
  const data = preview.data;
  const dealer = data.partner.name ?? "The dealer";
  if (data.commissionPct === null) {
    return (
      <CommissionCard description={`${dealer}'s commission and TOD for this application.`}>
        <Notice tone="warning">
          <p className="font-medium">No commission rate is in force for {dealer}</p>
          <p>
            {canAddRate ? (
              <>
                Add one for the {application.scheme} scheme in{" "}
                <Link
                  href="/subsidy-masters?table=commission"
                  className="font-medium text-primary-text underline-offset-4 hover:underline"
                >
                  Subsidy masters → Commission rates
                </Link>
                , from a date on or before the full-FP date.
              </>
            ) : (
              "Ask an administrator to add one; then it can be recorded."
            )}
          </p>
        </Notice>
      </CommissionCard>
    );
  }
  return (
    <CommissionCard
      description={`${dealer}'s commission and TOD for this application, at the rate in force on the full-FP date.`}
    >
      {canRecord ? (
        <RecordForm application={application} preview={data} existing={null} onDone={null} />
      ) : (
        <p className="text-sm text-muted-foreground">
          Not recorded yet. The subsidy co-ordinator records it, then Accounts approves and pays.
        </p>
      )}
    </CommissionCard>
  );
}

/** Recorded: its figures, where it stands, and what may be done next. */
function RecordedCommission({
  application,
  commission,
}: {
  application: Application;
  commission: Commission;
}): React.JSX.Element {
  const canRecord = useCan("subsidy", "edit");
  const [editing, setEditing] = useState(false);
  const again =
    canRecord && (commission.status === "calculated" || commission.status === "returned");

  return (
    <CommissionCard
      description={`${commission.partner.name ?? "The dealer"}'s commission and TOD for this application.`}
      badge={<CommissionStatusBadge status={commission.status} />}
    >
      {commission.status === "returned" ? (
        <Notice tone="warning">
          <p className="font-medium">
            Returned by {commission.decidedBy?.name ?? "Accounts"}
            {commission.decidedAt === null ? null : (
              <>
                {" "}
                <RelativeDate value={commission.decidedAt} />
              </>
            )}
          </p>
          <p>{commission.decisionRemark ?? "No remark."}</p>
          {again ? <p className="text-muted-foreground">Correct it and record it again.</p> : null}
        </Notice>
      ) : null}

      {editing ? (
        <EditAgain
          application={application}
          commission={commission}
          onDone={() => {
            setEditing(false);
          }}
        />
      ) : (
        <>
          <CommissionFigures figures={commission} label="The commission" className="max-w-md" />
          <RecordedFacts commission={commission} />
          <div className="flex flex-wrap items-center gap-2">
            {again ? (
              <Button
                variant="outline"
                onClick={() => {
                  setEditing(true);
                }}
              >
                Record it again
              </Button>
            ) : null}
            <CommissionActions commission={commission} />
          </div>
        </>
      )}
    </CommissionCard>
  );
}

function RecordedFacts({ commission }: { commission: Commission }): React.JSX.Element {
  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      <div className="flex flex-col gap-0.5">
        <dt className="text-xs text-muted-foreground">Recorded</dt>
        <dd className="text-foreground">
          {commission.recordedBy.name ?? "Someone"} · <RelativeDate value={commission.recordedAt} />
        </dd>
      </div>
      {commission.status === "approved" || commission.status === "paid" ? (
        <div className="flex flex-col gap-0.5">
          <dt className="text-xs text-muted-foreground">Approved</dt>
          <dd className="text-foreground">
            {commission.decidedBy?.name ?? "Accounts"}
            {commission.decidedAt === null ? null : (
              <>
                {" · "}
                <RelativeDate value={commission.decidedAt} />
              </>
            )}
          </dd>
        </div>
      ) : null}
      {commission.status === "paid" ? (
        <div className="flex flex-col gap-0.5">
          <dt className="text-xs text-muted-foreground">Paid</dt>
          <dd className="text-foreground">
            {commission.paidOn === null ? "—" : formatBusinessDay(commission.paidOn)}
            {commission.paymentReference === null ? null : (
              <span className="block font-mono text-xs text-muted-foreground">
                {commission.paymentReference}
              </span>
            )}
          </dd>
        </div>
      ) : null}
      {commission.remark === null ? null : (
        <div className="flex flex-col gap-0.5 sm:col-span-2">
          <dt className="text-xs text-muted-foreground">Remark</dt>
          <dd className="whitespace-pre-line text-foreground">{commission.remark}</dd>
        </div>
      )}
    </dl>
  );
}

/** Recording again needs the rate in force, so it reads the preview first. */
function EditAgain({
  application,
  commission,
  onDone,
}: {
  application: Application;
  commission: Commission;
  onDone: () => void;
}): React.JSX.Element {
  const preview = useQuery(commissionPreviewQueryOptions(application.id));
  if (preview.status === "pending") {
    return <Skeleton className="h-40 w-full" />;
  }
  if (preview.status === "error") {
    return (
      <ErrorState
        error={preview.error}
        onRetry={() => {
          void preview.refetch();
        }}
        className="border-0 p-2"
      />
    );
  }
  return (
    <RecordForm
      application={application}
      preview={preview.data}
      existing={commission}
      onDone={onDone}
    />
  );
}

type FormField = "gi_fitting" | "pvc_hdpe_fitting" | "installation" | "tod_base" | "remark";

function RecordForm({
  application,
  preview,
  existing,
  onDone,
}: {
  application: Application;
  preview: CommissionPreview;
  existing: Commission | null;
  /** Null when this is the first record: the card swaps to the recorded view by itself. */
  onDone: (() => void) | null;
}): React.JSX.Element {
  const record = useRecordCommission();
  const idempotency = useIdempotencyKey();
  const [gi, setGi] = useState(existing?.giFitting ?? "");
  const [pvc, setPvc] = useState(existing?.pvcHdpeFitting ?? "");
  const [installation, setInstallation] = useState(
    existing === null || existing.installation === preview.installation
      ? ""
      : existing.installation,
  );
  const [todBase, setTodBase] = useState(
    existing === null || existing.todBase === existing.commissionBase ? "" : existing.todBase,
  );
  const [remark, setRemark] = useState(existing?.remark ?? "");
  const [shown, setShown] = useState(false);
  const [serverFields, setServerFields] = useState<Partial<Record<FormField, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);

  // A half-typed amount counts as 0 in the working; its field says what is wrong.
  const number = (value: string): number => {
    const parsed = Number(value.trim() === "" ? "0" : value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const installationUsed =
    installation.trim() === "" ? Number(preview.installation) : number(installation);
  const deductions = number(gi) + number(pvc) + installationUsed;
  const cost = Number(preview.costExclGst);
  const problems: Record<FormField, string | null> = {
    gi_fitting:
      moneyProblem(gi, true) ??
      (deductions > cost
        ? `The fittings and installation come to more than the cost before GST, ${formatInr(preview.costExclGst, { paise: true })}.`
        : null),
    pvc_hdpe_fitting: moneyProblem(pvc, true),
    installation: moneyProblem(installation, false),
    tod_base: moneyProblem(todBase, false),
    remark: null,
  };
  const problemOf = (field: FormField): string | null =>
    serverFields[field] ?? (shown ? problems[field] : null);
  const valid = Object.values(problems).every((problem) => problem === null);
  const figures = workOutCommission({
    costExclGst: preview.costExclGst,
    giFitting: number(gi),
    pvcHdpeFitting: number(pvc),
    installation: installationUsed,
    todBase: todBase.trim() === "" ? null : number(todBase),
    commissionPct: preview.commissionPct ?? "0",
    todPct: preview.todPct ?? "0",
  });

  const submit = useAsyncAction({
    action: () => {
      const body = {
        gi_fitting: gi.trim(),
        pvc_hdpe_fitting: pvc.trim(),
        installation: installation.trim() === "" ? null : installation.trim(),
        tod_base: todBase.trim() === "" ? null : todBase.trim(),
        remark: remark.trim() === "" ? null : remark.trim(),
      };
      return record.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor({ applicationId: application.id, ...body }),
      });
    },
    logger: log,
    fn: "handleRecordCommission",
    dataId: "SUBS-016",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(existing === null ? "Commission recorded" : "Commission recorded again", {
        description: `${formatInr(saved.total, { paise: true })} to ${saved.partner.name ?? "the dealer"}. It waits for Accounts to approve.`,
      });
      onDone?.();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null && Object.keys(fields).length > 0) {
        setServerFields(fields);
        return;
      }
      if (isApiError(error) && error.code === "commission_exists") {
        setRefusal("It was approved meanwhile, so it can't be recorded again. Reload to see it.");
        return;
      }
      if (isApiError(error) && error.code === "no_rate") {
        setRefusal("The rate was retired meanwhile. Ask an administrator to add one.");
        return;
      }
      setRefusal(toUserFacingError(error).title);
    },
  });

  const clearField = (field: FormField): void => {
    setServerFields(({ [field]: _cleared, ...rest }) => rest);
  };

  return (
    <form
      noValidate
      aria-label={existing === null ? "Record the commission" : "Record the commission again"}
      className="grid gap-5 lg:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (!valid) return;
        void submit.run();
      }}
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <MoneyField
            id="commission-gi"
            label="GI fittings"
            placeholder="0"
            value={gi}
            error={problemOf("gi_fitting")}
            onChange={(next) => {
              setGi(next);
              clearField("gi_fitting");
            }}
          />
          <MoneyField
            id="commission-pvc"
            label="PVC and HDPE fittings"
            placeholder="0"
            value={pvc}
            error={problemOf("pvc_hdpe_fitting")}
            onChange={(next) => {
              setPvc(next);
              clearField("pvc_hdpe_fitting");
            }}
          />
          <MoneyField
            id="commission-installation"
            label="Installation"
            optional
            placeholder={preview.installation}
            description={`Empty: ${formatInr(preview.installation, { paise: true })}, from the calculation.`}
            value={installation}
            error={problemOf("installation")}
            onChange={(next) => {
              setInstallation(next);
              clearField("installation");
            }}
          />
          <MoneyField
            id="commission-tod-base"
            label="TOD base"
            optional
            description="Empty: the same as the commission base."
            value={todBase}
            error={problemOf("tod_base")}
            onChange={(next) => {
              setTodBase(next);
              clearField("tod_base");
            }}
          />
        </div>
        <Field>
          <FieldLabel htmlFor="commission-note">
            Remark <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="commission-note"
            rows={2}
            maxLength={500}
            value={remark}
            onChange={(event) => {
              setRemark(event.target.value);
            }}
          />
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            state={submit.state}
            loadingLabel="Recording…"
            successLabel="Recorded"
            errorLabel="Not recorded"
          >
            {existing === null ? "Record commission" : "Record it again"}
          </Button>
          {onDone === null ? null : (
            <Button type="button" variant="outline" disabled={submit.isBusy} onClick={onDone}>
              Keep it as it was
            </Button>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2 rounded-lg bg-muted p-4">
        <p className="text-xs font-medium text-muted-foreground">
          Worked out as you type · {preview.partner.name ?? "the dealer"}&apos;s rate
        </p>
        <CommissionFigures
          label="The commission as typed"
          figures={{
            costExclGst: preview.costExclGst,
            giFitting: rupees(Math.round(number(gi) * 100)),
            pvcHdpeFitting: rupees(Math.round(number(pvc) * 100)),
            installation: rupees(Math.round(installationUsed * 100)),
            commissionBase: rupees(figures.base),
            commissionPct: preview.commissionPct ?? "0",
            commissionAmount: rupees(figures.commission),
            todBase: rupees(figures.todBase),
            todPct: preview.todPct ?? "0",
            todAmount: rupees(figures.tod),
            total: rupees(figures.total),
          }}
        />
      </div>
    </form>
  );
}
