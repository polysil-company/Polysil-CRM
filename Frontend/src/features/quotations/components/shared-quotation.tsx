"use client";

import {
  AlertCircleIcon,
  InformationCircleIcon,
  LinkBackwardIcon,
  Pdf01Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { publicQuotationQueryOptions } from "@/features/quotations/api/quotations.queries";
import type { PublicQuotation } from "@/features/quotations/api/quotations.schemas";
import { isApiError } from "@/lib/api/errors";
import { asApiPath, buildApiUrl } from "@/lib/api/url";
import { formatFullDate, formatInr, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface SharedQuotationProps {
  /** The secret from the link: `/q/{token}`. */
  token: string;
}

/**
 * QUOT-012 · What a customer sees when they open the link they were sent: the number, who it
 * is from, the total, how long it is valid, and a button to the PDF. Nothing personal is on
 * the page — a forwarded link shows a number and a total, no more.
 *
 * The PDF opens only from the button, never on load: messengers fetch a link to draw its
 * preview, and that must not count as the customer opening it. Expired and replaced
 * quotations still open, with a note saying so.
 */
export function SharedQuotation({ token }: SharedQuotationProps): React.JSX.Element {
  const query = useQuery(publicQuotationQueryOptions(token));

  if (query.status === "error" && isApiError(query.error) && query.error.status === 404) {
    return (
      <EmptyState
        icon={LinkBackwardIcon}
        title="This link doesn't open a quotation"
        description="Check that you opened the whole link from the message, or ask the person who sent it for a new one."
        className="rounded-2xl border border-dashed border-border"
      />
    );
  }

  return (
    <QueryView
      query={query}
      pending={<SharedQuotationSkeleton />}
      isEmpty={() => false}
      empty={null}
    >
      {(quotation) => <SharedQuotationView quotation={quotation} />}
    </QueryView>
  );
}

function SharedQuotationView({ quotation }: { quotation: PublicQuotation }): React.JSX.Element {
  const path = asApiPath(quotation.pdfPath);
  const pdfHref = path === null ? null : buildApiUrl(path);

  return (
    <article
      aria-labelledby="shared-quotation-title"
      className="flex flex-col gap-5 rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7"
    >
      <header className="flex flex-col gap-1">
        <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
          Quotation
        </p>
        <h1
          id="shared-quotation-title"
          className="font-mono text-lg font-semibold wrap-break-word text-foreground sm:text-xl"
        >
          {quotation.quoteNo}
          {quotation.version > 1 ? (
            <span className="text-muted-foreground"> · v{quotation.version}</span>
          ) : null}
        </h1>
        <p className="text-sm text-muted-foreground">
          From <span className="text-foreground">{quotation.seller.legalName}</span>
          <span className="block font-mono text-xs">GSTIN {quotation.seller.gstin}</span>
        </p>
      </header>

      <div className="flex flex-col gap-1 rounded-xl bg-muted p-4">
        <p className="text-xs text-muted-foreground">Total, including GST</p>
        <p className="text-3xl font-semibold text-foreground tabular-nums">
          {formatInr(quotation.totals.total, { paise: true })}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <Fact label="Items">{formatNumber(quotation.lineCount)}</Fact>
        <Fact label="Sent">
          {quotation.sentAt === null ? "—" : formatFullDate(quotation.sentAt)}
        </Fact>
        <Fact label="Valid until" className="col-span-2">
          {quotation.validUntil === null ? "—" : formatFullDate(quotation.validUntil)}
        </Fact>
      </dl>

      {quotation.superseded ? (
        <Note tone="info">
          A newer version of this quotation was sent. Ask for its link; this one still opens.
        </Note>
      ) : null}
      {quotation.expired ? (
        <Note tone="warning">
          {quotation.validUntil === null
            ? "This quotation has expired."
            : `This quotation expired on ${formatFullDate(quotation.validUntil)}.`}{" "}
          Prices may have changed; ask for a new one.
        </Note>
      ) : null}

      <div className="flex flex-col gap-2">
        {quotation.pdfReady && pdfHref !== null ? (
          <a
            href={pdfHref}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ size: "lg", className: "w-full" })}
          >
            <Icon icon={Pdf01Icon} />
            View quotation
          </a>
        ) : (
          <>
            <span
              aria-disabled="true"
              className={buttonVariants({
                size: "lg",
                variant: "secondary",
                className: "pointer-events-none w-full",
              })}
            >
              <Spinner />
              Preparing the PDF…
            </span>
            <p role="status" className="text-center text-xs text-muted-foreground">
              It is usually ready in a few seconds. This page checks by itself.
            </p>
          </>
        )}
        {quotation.pdfReady ? (
          <p className="text-center text-xs text-muted-foreground">
            Opens the full quotation as a PDF in a new tab.
          </p>
        ) : null}
      </div>
    </article>
  );
}

function Fact({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium text-foreground">{children}</dd>
    </div>
  );
}

function Note({
  tone,
  children,
}: {
  tone: "info" | "warning";
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <p
      className={cn(
        "flex items-start gap-2 rounded-lg p-3 text-sm text-foreground",
        tone === "info" ? "bg-info-soft" : "bg-warning-soft",
      )}
    >
      <Icon
        icon={tone === "info" ? InformationCircleIcon : AlertCircleIcon}
        className={cn("mt-0.5", tone === "info" ? "text-info" : "text-warning")}
      />
      <span>{children}</span>
    </p>
  );
}

export function SharedQuotationSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading the quotation"
      className="flex flex-col gap-5 rounded-2xl border border-border bg-card p-5 sm:p-7"
    >
      <div className="flex flex-col gap-2">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-4 w-40" />
      </div>
      <Skeleton className="h-20 w-full rounded-xl" />
      <div className="grid grid-cols-2 gap-3">
        <Skeleton className="h-9" />
        <Skeleton className="h-9" />
      </div>
      <Skeleton className="h-11 w-full" />
    </div>
  );
}
