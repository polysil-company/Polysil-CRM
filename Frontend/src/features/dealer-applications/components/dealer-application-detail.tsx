"use client";

import { ArrowLeft01Icon, UserAdd01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { dealerApplicationQueryOptions } from "@/features/dealer-applications/api/dealer-applications.queries";
import {
  OPEN_STATUSES,
  type DealerApplication,
} from "@/features/dealer-applications/api/dealer-applications.schemas";
import {
  DEALER_APPLICATION_STATUS_BADGE,
  DEALER_APPLICATION_STATUS_LABELS,
  FIRM_TYPE_LABELS,
  missingLabel,
} from "@/features/dealer-applications/lib/dealer-application-labels";
import { RecordDocuments } from "@/features/documents/components/record-documents";
import { isApiError } from "@/lib/api/errors";
import { EMPTY_VALUE, formatFullDate, formatIndianPhone } from "@/lib/format";

import { DealerApplicationActions } from "./dealer-application-actions";

/**
 * CHNL-007 · One dealer application: where it stands and what is still needed, every field
 * the applicant (or staff for them) filled in, its documents, and what the reader may do.
 */
export function DealerApplicationDetail({
  applicationId,
}: {
  applicationId: string;
}): React.JSX.Element {
  const query = useQuery(dealerApplicationQueryOptions(applicationId));

  if (query.isError && isApiError(query.error) && query.error.status === 404) {
    return (
      <EmptyState
        icon={UserAdd01Icon}
        title="Application not found"
        description="It may be outside your area, or the link is wrong."
        action={
          <Link href="/partners/applications" className={buttonVariants({ variant: "outline" })}>
            All applications
          </Link>
        }
        className="rounded-xl border border-dashed border-border"
      />
    );
  }

  return (
    <QueryView
      query={query}
      pending={<DealerApplicationSkeleton />}
      isEmpty={() => false}
      empty={null}
    >
      {(application) => <DetailView application={application} />}
    </QueryView>
  );
}

function DetailView({ application }: { application: DealerApplication }): React.JSX.Element {
  const open = OPEN_STATUSES.some((status) => status === application.status);
  const label = DEALER_APPLICATION_STATUS_LABELS[application.status];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            href="/partners/applications"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            All applications
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold text-foreground">{application.firmName}</h2>
            <Badge variant={DEALER_APPLICATION_STATUS_BADGE[application.status]} dot>
              {label}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {application.contactName} · {formatIndianPhone(application.mobile)} ·{" "}
            {application.territory.name}
          </p>
        </div>
        <DealerApplicationActions application={application} />
      </div>

      <ApplicationNotices application={application} open={open} />

      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <Card>
          <CardHeader>
            <CardTitle level={3}>Firm and tax</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Fact label="Firm type">
                {application.firmType === null
                  ? "Not given"
                  : FIRM_TYPE_LABELS[application.firmType]}
              </Fact>
              <Fact label="GST">{application.gstRegistered ? "Registered" : "Not registered"}</Fact>
              <Fact label="GSTIN">
                {application.gstin === null ? (
                  EMPTY_VALUE
                ) : (
                  <span className="font-mono">{application.gstin}</span>
                )}
                {(application.gstNames?.tradeName ?? application.gstNames?.legalName) ? (
                  <span className="block text-xs text-muted-foreground">
                    GST record: {application.gstNames.tradeName ?? application.gstNames.legalName}
                  </span>
                ) : null}
              </Fact>
              <Fact label="PAN">
                {application.pan === null ? (
                  EMPTY_VALUE
                ) : (
                  <span className="font-mono">{application.pan}</span>
                )}
              </Fact>
              <Fact label="Years in business">
                {application.yearsInBusiness === null
                  ? EMPTY_VALUE
                  : String(application.yearsInBusiness)}
              </Fact>
              <Fact label="Brands sold now">{application.currentBrands ?? EMPTY_VALUE}</Fact>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle level={3}>Address and bank</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              <Fact label="Address" wide>
                {application.address ?? EMPTY_VALUE}
                {application.pincode === null ? null : ` ${application.pincode}`}
              </Fact>
              <Fact label="Godown" wide>
                {application.godownAddress ?? EMPTY_VALUE}
              </Fact>
              <Fact label="Email">{application.email ?? EMPTY_VALUE}</Fact>
              <Fact label="Bank account name">{application.bankAccountName ?? EMPTY_VALUE}</Fact>
              <Fact label="Account number">
                {application.bankAccountNo === null ? (
                  EMPTY_VALUE
                ) : (
                  <span className="font-mono">{application.bankAccountNo}</span>
                )}
              </Fact>
              <Fact label="IFSC">
                {application.bankIfsc === null ? (
                  EMPTY_VALUE
                ) : (
                  <span className="font-mono">{application.bankIfsc}</span>
                )}
              </Fact>
            </dl>
          </CardContent>
        </Card>
      </div>

      {application.notes === null ? null : (
        <Card>
          <CardHeader>
            <CardTitle level={3}>Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-line text-foreground">{application.notes}</p>
          </CardContent>
        </Card>
      )}

      <RecordDocuments
        scope={{
          kind: "record",
          recordType: "dealer_application",
          recordId: application.id,
        }}
        canAdd={application.can.edit}
        closed={!open}
        description="The GST certificate, PAN card and a cancelled cheque are needed; a shop photo or licence helps."
        emptyHint="No documents yet. Attach the GST certificate, PAN card and a cancelled cheque."
      />

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-0.5">
            <CardTitle level={3}>History</CardTitle>
            <CardDescription>Who started it, and who decided.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            <Fact label="Started">
              {formatFullDate(application.createdAt)}
              {application.createdBy === null ? null : (
                <span className="block text-xs text-muted-foreground">
                  by {application.createdBy.name}
                </span>
              )}
            </Fact>
            <Fact label="Decided">
              {application.decidedAt === null ? "Not yet" : formatFullDate(application.decidedAt)}
              {application.decidedBy === null ? null : (
                <span className="block text-xs text-muted-foreground">
                  by {application.decidedBy.name}
                </span>
              )}
            </Fact>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

function ApplicationNotices({
  application,
  open,
}: {
  application: DealerApplication;
  open: boolean;
}): React.JSX.Element | null {
  const notices: React.JSX.Element[] = [];
  const remark = application.decisionRemark;
  if (application.status === "returned") {
    notices.push(
      <Notice key="returned" tone="warning">
        <p className="font-medium">Returned to the applicant</p>
        {remark === null ? null : <p>{remark}</p>}
      </Notice>,
    );
  }
  if (application.status === "rejected" || application.status === "withdrawn") {
    notices.push(
      <Notice key="closed" tone="danger">
        <p className="font-medium">
          {application.status === "rejected" ? "Rejected" : "Withdrawn"}
        </p>
        {remark === null ? null : <p>{remark}</p>}
      </Notice>,
    );
  }
  if (application.status === "approved") {
    notices.push(
      <Notice key="approved" tone="success">
        <p className="font-medium">Approved: the dealer and its login are added</p>
        <p>
          They sign in with a WhatsApp code on {formatIndianPhone(application.mobile)}.
          {application.partnerId === null ? null : (
            <>
              {" "}
              <Link
                href={`/partners/${application.partnerId}`}
                className="text-primary-text underline underline-offset-4"
              >
                Open the dealer
              </Link>
            </>
          )}
        </p>
      </Notice>,
    );
  }
  if (application.gstStateMismatch) {
    notices.push(
      <Notice key="gst-state" tone="warning">
        <p>The GSTIN is registered in another state than {application.territory.name}.</p>
      </Notice>,
    );
  }
  if (open && application.missing.length > 0) {
    notices.push(
      <Notice key="missing" tone="info">
        <p className="font-medium">Still needed before it can be submitted</p>
        <p>{application.missing.map(missingLabel).join(", ")}.</p>
      </Notice>,
    );
  }
  if (application.status === "draft" || application.status === "returned") {
    notices.push(
      <p key="link" className="text-xs text-muted-foreground">
        The applicant&apos;s link works until {formatFullDate(application.linkExpiresAt)}.
      </p>,
    );
  }
  return notices.length === 0 ? null : <div className="flex flex-col gap-3">{notices}</div>;
}

function Fact({
  label,
  wide = false,
  children,
}: {
  label: string;
  wide?: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div
      className={
        wide ? "flex min-w-0 flex-col gap-0.5 sm:col-span-2" : "flex min-w-0 flex-col gap-0.5"
      }
    >
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}

export function DealerApplicationSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the application" className="flex flex-col gap-4">
      <Skeleton className="h-6 w-64" />
      <Skeleton className="h-4 w-80" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    </div>
  );
}
