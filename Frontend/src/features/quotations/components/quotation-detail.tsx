"use client";

import { ArrowLeft01Icon, Copy01Icon, Tick02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { partnerTypeLabel } from "@/features/leads/lib/lead-labels";
import { quotationDetailQueryOptions } from "@/features/quotations/api/quotations.queries";
import type { Quotation, QuotationLine } from "@/features/quotations/api/quotations.schemas";
import {
  PDF_STATE_LABELS,
  SALES_TYPE_LABELS,
  formatQuantity,
  formatRate,
  parseWarnings,
  quotationTitle,
} from "@/features/quotations/lib/quotation-labels";
import { draftSendNotice } from "@/features/quotations/lib/quotation-lifecycle";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { isApiError } from "@/lib/api/errors";
import {
  EMPTY_VALUE,
  formatFullDate,
  formatIndianPhone,
  formatInr,
  formatNumber,
} from "@/lib/format";
import { cn } from "@/lib/utils";

import { QuotationActions } from "./quotation-actions";
import { QuotationHistory } from "./quotation-history";
import { QuotationStatusBadge } from "./quotation-status-badge";
import { QuotationVersions } from "./quotation-versions";

/** QUOT-002 · The quotation as the backend prints it. A 404 renders the route's not-found page. */
export function QuotationDetail({ quotationId }: { quotationId: string }): React.JSX.Element {
  const query = useQuery(quotationDetailQueryOptions(quotationId));

  if (query.status === "error" && isApiError(query.error) && query.error.status === 404) {
    notFound();
  }

  return (
    <QueryView
      query={query}
      pending={<QuotationDetailSkeleton />}
      isEmpty={() => false}
      empty={null}
    >
      {(quotation) => <QuotationDetailView quotation={quotation} />}
    </QueryView>
  );
}

function QuotationDetailView({ quotation }: { quotation: Quotation }): React.JSX.Element {
  const sent = quotation.status !== "draft";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            href="/quotations"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            All quotations
          </Link>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="truncate font-mono text-xl font-semibold text-foreground">
              {quotationTitle(quotation)}
            </h2>
            <QuotationStatusBadge status={quotation.status} />
            <Badge variant="outline">{SALES_TYPE_LABELS[quotation.salesType]}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            For {quotation.party.name} ·{" "}
            {quotation.lead === null ? (
              "lead not visible"
            ) : (
              <Link
                href={`/leads/${quotation.lead.id}`}
                className="font-mono text-primary-text underline-offset-4 hover:underline"
              >
                {quotation.lead.code}
              </Link>
            )}
          </p>
        </div>
        <QuotationActions quotation={quotation} />
      </div>

      <QuotationNotices quotation={quotation} />

      <Card>
        <CardHeader>
          <CardTitle level={3}>
            Items{" "}
            <span className="font-normal text-muted-foreground">
              ({formatNumber(quotation.lines.length)})
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {quotation.lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">No items yet. This draft is empty.</p>
          ) : (
            <>
              <LineCards lines={quotation.lines} intraState={quotation.intraState} />
              <LineTable lines={quotation.lines} intraState={quotation.intraState} />
            </>
          )}
          <TotalsBlock quotation={quotation} />
        </CardContent>
      </Card>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle level={3}>Party</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-3">
                <DetailItem label="Name">{quotation.party.name}</DetailItem>
                <DetailItem label="Mobile">
                  {quotation.party.mobile === ""
                    ? EMPTY_VALUE
                    : formatIndianPhone(quotation.party.mobile)}
                </DetailItem>
                <DetailItem label="Address">{quotation.party.address ?? EMPTY_VALUE}</DetailItem>
                {quotation.party.gstin === null ? null : (
                  <DetailItem label="GSTIN">
                    <span className="font-mono">{quotation.party.gstin}</span>
                  </DetailItem>
                )}
              </dl>
            </CardContent>
          </Card>
          {quotation.terms === null || quotation.terms.trim() === "" ? null : (
            <Card>
              <CardHeader>
                <CardTitle level={3}>Terms</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-line text-foreground">{quotation.terms}</p>
              </CardContent>
            </Card>
          )}
          <QuotationVersions quotation={quotation} />
        </div>
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle level={3}>Details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                <DetailItem label="Owner">
                  {quotation.owner === null ? (
                    <span className="text-muted-foreground">
                      Unassigned · {quotation.ownerOrgUnit.name}
                    </span>
                  ) : (
                    <AvatarLabel
                      name={quotation.owner.name}
                      secondary={quotation.ownerOrgUnit.name}
                      size="xs"
                    />
                  )}
                </DetailItem>
                <DetailItem label="Channel partner">
                  {quotation.partner === null
                    ? "Direct sale"
                    : `${quotation.partner.name}${quotation.partner.partnerType === null ? "" : ` · ${partnerTypeLabel(quotation.partner.partnerType)}`}`}
                </DetailItem>
                <DetailItem label="Place of supply">
                  {quotation.placeOfSupply.territory.name} · {quotation.placeOfSupply.state}
                  <span className="block text-xs text-muted-foreground">
                    {quotation.intraState
                      ? "Within the state: CGST and SGST"
                      : "Across states: IGST"}
                  </span>
                </DetailItem>
                <DetailItem label="Seller">
                  {quotation.seller.legalName}
                  <span className="block font-mono text-xs text-muted-foreground">
                    {quotation.seller.gstin}
                  </span>
                </DetailItem>
                <DetailItem label="Prices as of">
                  {formatFullDate(quotation.priceEffectiveDate)}
                  {quotation.priceList === null ? null : (
                    <span className="block text-xs text-muted-foreground">
                      {quotation.priceList.name}
                    </span>
                  )}
                </DetailItem>
                <DetailItem label="Valid until">
                  {quotation.validUntil === null
                    ? "Set when sent"
                    : formatFullDate(quotation.validUntil)}
                </DetailItem>
                <DetailItem label="Sent">
                  {quotation.sentAt === null ? (
                    "Not yet"
                  ) : (
                    <RelativeDate value={quotation.sentAt} />
                  )}
                </DetailItem>
                {sent ? (
                  <DetailItem label="Opened by the customer">
                    {quotation.viewedAt === null ? (
                      "Not yet"
                    ) : (
                      <>
                        <RelativeDate value={quotation.viewedAt} />
                        <span className="text-muted-foreground">
                          {" "}
                          ·{" "}
                          {quotation.openCount === 1
                            ? "once"
                            : `${formatNumber(quotation.openCount)} times`}
                        </span>
                      </>
                    )}
                  </DetailItem>
                ) : null}
                <DetailItem label="Created">
                  {formatFullDate(quotation.createdAt)}
                  {quotation.createdBy === null ? null : (
                    <span className="text-muted-foreground"> · by {quotation.createdBy.name}</span>
                  )}
                </DetailItem>
              </dl>
              {quotation.shareUrl === null ? null : <ShareLink url={quotation.shareUrl} />}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle level={3}>History</CardTitle>
            </CardHeader>
            <CardContent>
              <QuotationHistory quotationId={quotation.id} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function DetailItem({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}

/** Everything the reader must know before trusting the figures, most important first. */
function QuotationNotices({ quotation }: { quotation: Quotation }): React.JSX.Element | null {
  const warnings = parseWarnings(quotation.warnings).filter(
    // The provisional banner says this one already.
    (warning) => warning.code !== "provisional_pricing",
  );
  const notices: React.ReactNode[] = [];
  const sendNotice = draftSendNotice(quotation);

  if (sendNotice !== null) {
    notices.push(
      <Notice key="send" tone={sendNotice.tone}>
        <p className="font-medium">{sendNotice.title}</p>
        {sendNotice.detail === null ? null : (
          <p className="text-muted-foreground">{sendNotice.detail}</p>
        )}
      </Notice>,
    );
  }
  if (quotation.supersededBy !== null) {
    notices.push(
      <Notice key="superseded" tone="info">
        <p>
          Version {quotation.supersededBy.version} replaced this one.{" "}
          <Link
            href={`/quotations/${quotation.supersededBy.id}`}
            className="font-medium text-primary-text underline-offset-4 hover:underline"
          >
            Open version {quotation.supersededBy.version}
          </Link>
        </p>
      </Notice>,
    );
  }
  if (quotation.isProvisional) {
    notices.push(
      <Notice key="provisional" tone="warning">
        <p className="font-medium">Indicative pricing</p>
        <p className="text-muted-foreground">
          Some rates or tax slabs are stand-ins until the price list is confirmed. The PDF carries
          the same banner.
        </p>
      </Notice>,
    );
  }
  if (quotation.status === "accepted" || quotation.status === "rejected") {
    const decidedAt = quotation.status === "accepted" ? quotation.acceptedAt : quotation.rejectedAt;
    notices.push(
      <Notice key="decision" tone={quotation.status === "accepted" ? "success" : "danger"}>
        <p className="font-medium">
          {quotation.status === "accepted"
            ? "Accepted by the customer"
            : "Rejected by the customer"}
          {decidedAt === null ? null : <> · {formatFullDate(decidedAt)}</>}
          {quotation.decidedBy === null ? null : <> · recorded by {quotation.decidedBy.name}</>}
        </p>
        {quotation.decisionRemark === null ? null : (
          <p className="whitespace-pre-line text-muted-foreground">{quotation.decisionRemark}</p>
        )}
      </Notice>,
    );
  }
  if (quotation.pdfState === "failed") {
    notices.push(
      <Notice key="pdf" tone="danger">
        <p className="font-medium">{PDF_STATE_LABELS.failed}</p>
        {quotation.pdfError === null ? null : (
          <p className="text-muted-foreground">{quotation.pdfError}</p>
        )}
      </Notice>,
    );
  }
  if (quotation.pdfState === "pending") {
    notices.push(
      <Notice key="pdf" tone="info">
        <p>
          {PDF_STATE_LABELS.pending} It is usually ready within a few seconds; this page checks
          again by itself.
        </p>
      </Notice>,
    );
  }
  for (const [index, warning] of warnings.entries()) {
    notices.push(
      <Notice key={`warning-${String(index)}`} tone="warning">
        <p>{warning.message}</p>
      </Notice>,
    );
  }

  return notices.length === 0 ? null : <div className="flex flex-col gap-2">{notices}</div>;
}

/** The tiers any line uses: tier 1 always shows, 2 and 3 only when a line carries them. */
function usedTiers(lines: readonly QuotationLine[]): number[] {
  return [0, 1, 2].filter(
    (tier) => tier === 0 || lines.some((line) => Number(line.discounts[tier]?.pct ?? "0") !== 0),
  );
}

/** "−₹185.74" for a discount; "₹0.00" when there is none, without a stray minus. */
function formatDiscount(amount: string): string {
  const text = formatInr(amount, { paise: true });
  return Number(amount) === 0 ? text : `−${text}`;
}

function gstLabel(line: QuotationLine, intraState: boolean): string {
  return intraState
    ? `CGST ${formatRate(line.cgst.rate)} + SGST ${formatRate(line.sgst.rate)}`
    : `IGST ${formatRate(line.igst.rate)}`;
}

function gstAmount(line: QuotationLine, intraState: boolean): string {
  return intraState
    ? formatInr(line.cgst.amount, { paise: true }) +
        " + " +
        formatInr(line.sgst.amount, { paise: true })
    : formatInr(line.igst.amount, { paise: true });
}

/** Wider screens: the client's own columns, in their order. */
function LineTable({
  lines,
  intraState,
}: {
  lines: readonly QuotationLine[];
  intraState: boolean;
}): React.JSX.Element {
  const tiers = usedTiers(lines);
  const headCell = "px-3 py-2 text-left text-xs font-medium text-muted-foreground";
  const numHead = cn(headCell, "text-right");
  const cell = "px-3 py-2.5 align-top text-sm";
  const numCell = cn(cell, "text-right whitespace-nowrap tabular-nums");

  return (
    <div className="hidden overflow-x-auto rounded-lg border border-border md:block">
      <table className="w-full min-w-max border-collapse">
        <caption className="sr-only">Quotation items with discounts and tax</caption>
        <thead className="bg-panel">
          <tr>
            <th scope="col" className={headCell}>
              #
            </th>
            <th scope="col" className={headCell}>
              Item
            </th>
            <th scope="col" className={numHead}>
              Qty
            </th>
            <th scope="col" className={numHead}>
              Rate
            </th>
            <th scope="col" className={numHead}>
              Gross
            </th>
            {tiers.map((tier) => (
              <th key={tier} scope="col" className={numHead}>
                {tier === 0 ? "1st disc." : tier === 1 ? "2nd disc." : "3rd disc."}
              </th>
            ))}
            <th scope="col" className={numHead}>
              Taxable
            </th>
            <th scope="col" className={numHead}>
              GST
            </th>
            <th scope="col" className={numHead}>
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.lineNo} className="border-t border-border">
              <td className={cn(cell, "text-muted-foreground tabular-nums")}>{line.lineNo}</td>
              <th scope="row" className={cn(cell, "min-w-56 text-left font-normal")}>
                <span className="block font-medium text-foreground">{line.description}</span>
                <span className="block text-xs text-muted-foreground">
                  HSN {line.hsnCode} · {line.uom}
                  {line.provisionalFields.length > 0 ? " · indicative" : ""}
                </span>
              </th>
              <td className={numCell}>{formatQuantity(line.qty)}</td>
              <td className={numCell}>{formatInr(line.rate, { paise: true })}</td>
              <td className={numCell}>{formatInr(line.gross, { paise: true })}</td>
              {tiers.map((tier) => {
                const discount = line.discounts[tier];
                return (
                  <td key={tier} className={numCell}>
                    {discount === undefined ? (
                      EMPTY_VALUE
                    ) : (
                      <>
                        <span className="block">{formatRate(discount.pct)}</span>
                        <span className="block text-xs text-muted-foreground">
                          {formatDiscount(discount.amount)}
                        </span>
                      </>
                    )}
                  </td>
                );
              })}
              <td className={numCell}>{formatInr(line.taxable, { paise: true })}</td>
              <td className={numCell}>
                <span className="block">{formatRate(line.gstSlab)}</span>
                <span className="block text-xs text-muted-foreground">
                  {gstAmount(line, intraState)}
                </span>
              </td>
              <td className={cn(numCell, "font-medium")}>
                {formatInr(line.total, { paise: true })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Phones: one card per line, the same figures in reading order. */
function LineCards({
  lines,
  intraState,
}: {
  lines: readonly QuotationLine[];
  intraState: boolean;
}): React.JSX.Element {
  return (
    <ol aria-label="Quotation items" className="flex flex-col gap-3 md:hidden">
      {lines.map((line) => (
        <li key={line.lineNo} className="flex flex-col gap-2 rounded-lg border border-border p-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-foreground">
              {line.lineNo}. {line.description}
            </span>
            <span className="text-xs text-muted-foreground">
              HSN {line.hsnCode}
              {line.provisionalFields.length > 0 ? " · indicative" : ""}
            </span>
          </div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
            <dt className="text-muted-foreground">Qty × rate</dt>
            <dd className="text-right tabular-nums">
              {formatQuantity(line.qty)} {line.uom} × {formatInr(line.rate, { paise: true })}
            </dd>
            <dt className="text-muted-foreground">Gross</dt>
            <dd className="text-right tabular-nums">{formatInr(line.gross, { paise: true })}</dd>
            <dt className="text-muted-foreground">Discount</dt>
            <dd className="text-right tabular-nums">{formatDiscount(line.discount)}</dd>
            <dt className="text-muted-foreground">Taxable</dt>
            <dd className="text-right tabular-nums">{formatInr(line.taxable, { paise: true })}</dd>
            <dt className="text-muted-foreground">{gstLabel(line, intraState)}</dt>
            <dd className="text-right tabular-nums">{gstAmount(line, intraState)}</dd>
            <dt className="font-medium">Total</dt>
            <dd className="text-right font-medium tabular-nums">
              {formatInr(line.total, { paise: true })}
            </dd>
          </dl>
        </li>
      ))}
    </ol>
  );
}

function TotalsBlock({ quotation }: { quotation: Quotation }): React.JSX.Element {
  const { totals } = quotation;
  const rows: { label: string; value: string; strong?: boolean }[] = [
    { label: "Gross", value: formatInr(totals.gross, { paise: true }) },
    { label: "Discount", value: formatDiscount(totals.discount) },
    { label: "Taxable value", value: formatInr(totals.taxable, { paise: true }) },
    ...(quotation.intraState
      ? [
          { label: "CGST", value: formatInr(totals.cgst, { paise: true }) },
          { label: "SGST", value: formatInr(totals.sgst, { paise: true }) },
        ]
      : [{ label: "IGST", value: formatInr(totals.igst, { paise: true }) }]),
    { label: "Total", value: formatInr(totals.total, { paise: true }), strong: true },
  ];

  return (
    <dl
      aria-label="Totals"
      className="ml-auto grid w-full max-w-sm grid-cols-2 gap-x-4 gap-y-1.5 text-sm"
    >
      {rows.map((row) => (
        <div
          key={row.label}
          className={cn(
            "col-span-2 grid grid-cols-subgrid",
            row.strong && "border-t border-border pt-2",
          )}
        >
          <dt className={row.strong ? "font-semibold text-foreground" : "text-muted-foreground"}>
            {row.label}
          </dt>
          <dd
            className={cn(
              "text-right tabular-nums",
              row.strong ? "text-base font-semibold" : "text-foreground",
            )}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ShareLink({ url }: { url: string }): React.JSX.Element {
  const { copied, copy } = useCopyToClipboard();
  return (
    <div className="mt-4 flex flex-col gap-1.5 border-t border-border pt-4">
      <span className="text-xs text-muted-foreground">Customer link</span>
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">{url}</span>
        <Button
          variant="outline"
          size="sm"
          aria-label={copied ? "Link copied" : "Copy the customer link"}
          onClick={() => {
            void copy(url);
          }}
        >
          <Icon icon={copied ? Tick02Icon : Copy01Icon} />
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

/** Mirrors QuotationDetailView block for block. */
export function QuotationDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading quotation" className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-5 w-28" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-7 w-64" />
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
          <Skeleton className="h-5 w-72" />
        </div>
        <Skeleton className="h-control-md w-28 rounded-md" />
      </div>
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-24" />
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-12 w-full rounded-lg" />
          ))}
          <Skeleton className="ml-auto h-32 w-full max-w-sm rounded-lg" />
        </CardContent>
      </Card>
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-20" />
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {[0, 1, 2].map((row) => (
              <div key={row} className="flex flex-col gap-1">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-5 w-40" />
              </div>
            ))}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <Skeleton className="h-6 w-20" />
          </CardHeader>
          <CardContent className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
            {Array.from({ length: 8 }, (_, index) => (
              <div key={index} className="flex flex-col gap-1">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-5 w-40" />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
