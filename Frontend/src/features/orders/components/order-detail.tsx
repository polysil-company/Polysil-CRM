"use client";

import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import type * as React from "react";

import { AvatarLabel } from "@/components/patterns/avatar-label";
import { Notice } from "@/components/patterns/notice";
import { ProportionBar } from "@/components/patterns/proportion-bar";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { partnerTypeLabel } from "@/features/leads/lib/lead-labels";
import { orderDetailQueryOptions } from "@/features/orders/api/orders.queries";
import type { Order, OrderLine } from "@/features/orders/api/orders.schemas";
import {
  ORDER_PDF_LABELS,
  ORDER_TYPE_LABELS,
  PAYMENT_TERMS_LABELS,
  formatOrderQty,
  orderNumber,
  stepRoleLabel,
} from "@/features/orders/lib/order-labels";
import { formatRate, parseWarnings } from "@/features/quotations/lib/quotation-labels";
import { isApiError } from "@/lib/api/errors";
import {
  EMPTY_VALUE,
  formatFullDate,
  formatIndianPhone,
  formatInr,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { cn } from "@/lib/utils";

import { OrderActions } from "./order-actions";
import { OrderApproval } from "./order-approval";
import { OrderDispatches } from "./order-dispatches";
import { OrderHistory } from "./order-history";
import { OrderStatusBadge } from "./order-status-badge";

/** SO-002 · The order as the backend prints it. A 404 renders the route's not-found page. */
export function OrderDetail({ orderId }: { orderId: string }): React.JSX.Element {
  const query = useQuery(orderDetailQueryOptions(orderId));

  if (query.status === "error" && isApiError(query.error) && query.error.status === 404) {
    notFound();
  }

  return (
    <QueryView query={query} pending={<OrderDetailSkeleton />} isEmpty={() => false} empty={null}>
      {(order) => <OrderDetailView order={order} />}
    </QueryView>
  );
}

/** Share of the ordered quantity sent, 0 to 100, from the lines the backend sent. */
function shippedPercent(lines: readonly OrderLine[]): number {
  const ordered = lines.reduce((sum, line) => sum + Number(line.qty), 0);
  const sent = lines.reduce((sum, line) => sum + Number(line.qtyDispatched), 0);
  return ordered === 0 ? 0 : Math.floor((sent / ordered) * 100);
}

function OrderDetailView({ order }: { order: Order }): React.JSX.Element {
  const shipping = order.approvedAt !== null && order.status !== "cancelled";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            href="/sales-orders"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            All orders
          </Link>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2
              className={cn(
                "truncate text-xl font-semibold text-foreground",
                order.orderNo !== null && "font-mono",
              )}
            >
              {orderNumber(order)}
            </h2>
            <OrderStatusBadge status={order.status} />
            <Badge variant="outline">{ORDER_TYPE_LABELS[order.orderType]}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            For {order.party.name}
            {order.lead === null ? null : (
              <>
                {" · "}
                <Link
                  href={`/leads/${order.lead.id}`}
                  className="font-mono text-primary-text underline-offset-4 hover:underline"
                >
                  {order.lead.code}
                </Link>
              </>
            )}
          </p>
        </div>
        <OrderActions order={order} />
      </div>

      <OrderNotices order={order} />

      {order.approval === null ? null : <OrderApproval order={order} />}

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle level={3}>
            Items{" "}
            <span className="font-normal text-muted-foreground">
              ({formatNumber(order.lines.length)})
            </span>
          </CardTitle>
          {shipping ? <ShippedMeter lines={order.lines} /> : null}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {order.lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">No items yet — this draft is empty.</p>
          ) : (
            <>
              <LineCards lines={order.lines} intraState={order.intraState} shipping={shipping} />
              <LineTable lines={order.lines} intraState={order.intraState} shipping={shipping} />
            </>
          )}
          <TotalsBlock order={order} />
        </CardContent>
      </Card>

      {shipping ? <OrderDispatches order={order} /> : null}

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle level={3}>Party</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-3">
                <DetailItem label="Name">{order.party.name}</DetailItem>
                <DetailItem label="Mobile">
                  {order.party.mobile === null
                    ? EMPTY_VALUE
                    : formatIndianPhone(order.party.mobile)}
                </DetailItem>
                <DetailItem label="Address">{order.party.address ?? EMPTY_VALUE}</DetailItem>
                {order.party.gstin === null ? null : (
                  <DetailItem label="GSTIN">
                    <span className="font-mono">{order.party.gstin}</span>
                  </DetailItem>
                )}
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle level={3}>From quotations</CardTitle>
            </CardHeader>
            <CardContent>
              {order.quotations.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Typed in directly, or the quotations are not visible to you.
                </p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {order.quotations.map((quotation) => (
                    <li key={quotation.id}>
                      <Link
                        href={`/quotations/${quotation.id}`}
                        className="font-mono text-sm text-primary-text underline-offset-4 hover:underline"
                      >
                        {quotation.quoteNo ?? "Draft"}
                        {quotation.version > 1 ? ` · v${String(quotation.version)}` : ""}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle level={3}>Details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                <DetailItem label="Owner">
                  {order.owner === null ? (
                    <span className="text-muted-foreground">
                      Not visible · {order.ownerOrgUnit.name}
                    </span>
                  ) : (
                    <AvatarLabel
                      name={order.owner.name}
                      secondary={order.ownerOrgUnit.name}
                      size="xs"
                    />
                  )}
                </DetailItem>
                <DetailItem label="Channel partner">
                  {order.partner === null
                    ? "Direct sale"
                    : `${order.partner.name}${order.partner.partnerType === null ? "" : ` · ${partnerTypeLabel(order.partner.partnerType)}`}`}
                </DetailItem>
                <DetailItem label="Deliver to">
                  <span className="whitespace-pre-line">
                    {order.deliveryAddress ?? "Not given yet"}
                  </span>
                </DetailItem>
                <DetailItem label="Payment terms">
                  {PAYMENT_TERMS_LABELS[order.paymentTerms]}
                  <span className="block text-xs text-muted-foreground">
                    Recorded, not checked: there is no credit check.
                  </span>
                </DetailItem>
                <DetailItem label="Place of supply">
                  {order.placeOfSupply.name}
                  <span className="block text-xs text-muted-foreground">
                    {order.intraState ? "Within the state — CGST and SGST" : "Across states — IGST"}
                  </span>
                </DetailItem>
                <DetailItem label="Seller">
                  {order.seller === null ? (
                    "Set when submitted"
                  ) : (
                    <>
                      {order.seller.legalName}
                      <span className="block font-mono text-xs text-muted-foreground">
                        {order.seller.gstin}
                      </span>
                    </>
                  )}
                </DetailItem>
                <DetailItem label="Prices as of">
                  {formatFullDate(order.priceEffectiveDate)}
                </DetailItem>
                <DetailItem label="Submitted">
                  {order.submittedAt === null ? (
                    "Not yet"
                  ) : (
                    <RelativeDate value={order.submittedAt} />
                  )}
                </DetailItem>
                <DetailItem label="Approved">
                  {order.approvedAt === null ? (
                    "Not yet"
                  ) : (
                    <RelativeDate value={order.approvedAt} />
                  )}
                </DetailItem>
                <DetailItem label="Created">{formatFullDate(order.createdAt)}</DetailItem>
                {order.remarks === null ? null : (
                  <DetailItem label="Remarks" className="sm:col-span-2">
                    <span className="whitespace-pre-line">{order.remarks}</span>
                  </DetailItem>
                )}
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle level={3}>History</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderHistory orderId={order.id} />
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

function ShippedMeter({ lines }: { lines: readonly OrderLine[] }): React.JSX.Element {
  const percent = shippedPercent(lines);
  return (
    <div className="flex items-center gap-2 text-sm">
      <ProportionBar
        value={percent}
        max={100}
        tone={percent === 100 ? "success" : "primary"}
        className="h-1.5 w-24"
      />
      <span className="text-muted-foreground tabular-nums">{formatPercent(percent)} sent</span>
    </div>
  );
}

/** Everything the reader must know before trusting the order, most important first. */
function OrderNotices({ order }: { order: Order }): React.JSX.Element | null {
  const notices: React.ReactNode[] = [];

  if (order.status === "draft" && order.lastRejection !== null) {
    notices.push(
      <Notice key="returned" tone="danger">
        <p className="font-medium">
          Returned by {stepRoleLabel(order.lastRejection.role)} ·{" "}
          {formatFullDate(order.lastRejection.at)}
        </p>
        <p className="whitespace-pre-line text-muted-foreground">{order.lastRejection.remark}</p>
        <p className="text-muted-foreground">Make the changes asked for, then submit it again.</p>
      </Notice>,
    );
  }
  if (order.status === "cancelled") {
    notices.push(
      <Notice key="cancelled" tone="danger">
        <p className="font-medium">
          Cancelled{order.cancelledAt === null ? null : <> · {formatFullDate(order.cancelledAt)}</>}
        </p>
        {order.cancelRemark === null ? null : (
          <p className="whitespace-pre-line text-muted-foreground">{order.cancelRemark}</p>
        )}
      </Notice>,
    );
  }
  if (order.status === "closed_short") {
    notices.push(
      <Notice key="closed" tone="warning">
        <p className="font-medium">
          Closed short{order.closedAt === null ? null : <> · {formatFullDate(order.closedAt)}</>}
        </p>
        <p className="text-muted-foreground">
          What was still open will not ship.
          {order.closeRemark === null ? null : ` ${order.closeRemark}`}
        </p>
      </Notice>,
    );
  }
  if (order.isProvisional) {
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
  if (order.confirmation === "no_mobile" && order.approvedAt !== null) {
    notices.push(
      <Notice key="confirmation" tone="info">
        <p>
          The customer has no mobile number on the order, so no confirmation was sent. Share the PDF
          with them by hand.
        </p>
      </Notice>,
    );
  }
  if (order.pdfState === "failed") {
    notices.push(
      <Notice key="pdf" tone="danger">
        <p className="font-medium">{ORDER_PDF_LABELS.failed}</p>
        {order.pdfError === null ? null : <p className="text-muted-foreground">{order.pdfError}</p>}
      </Notice>,
    );
  }
  if (order.pdfState === "pending") {
    notices.push(
      <Notice key="pdf" tone="info">
        <p>
          {ORDER_PDF_LABELS.pending} It is usually ready within a few seconds; this page checks
          again by itself.
        </p>
      </Notice>,
    );
  }
  for (const [index, warning] of parseWarnings(order.warnings)
    .filter((item) => item.code !== "provisional_pricing")
    .entries()) {
    notices.push(
      <Notice key={`warning-${String(index)}`} tone="warning">
        <p>{warning.message}</p>
      </Notice>,
    );
  }

  return notices.length === 0 ? null : <div className="flex flex-col gap-2">{notices}</div>;
}

function gstAmount(line: OrderLine, intraState: boolean): string {
  return intraState
    ? `${formatInr(line.cgst.amount, { paise: true })} + ${formatInr(line.sgst.amount, { paise: true })}`
    : formatInr(line.igst.amount, { paise: true });
}

/** "−₹185.74" for a discount; "₹0.00" when there is none, without a stray minus. */
function formatDiscount(amount: string): string {
  const text = formatInr(amount, { paise: true });
  return Number(amount) === 0 ? text : `−${text}`;
}

function qty(line: OrderLine, value: string): string {
  return formatOrderQty(value, line.uomDecimals);
}

/** Wider screens: the order's figures, and once approved what has left and what is open. */
function LineTable({
  lines,
  intraState,
  shipping,
}: {
  lines: readonly OrderLine[];
  intraState: boolean;
  shipping: boolean;
}): React.JSX.Element {
  const headCell = "px-3 py-2 text-left text-xs font-medium text-muted-foreground";
  const numHead = cn(headCell, "text-right");
  const cell = "px-3 py-2.5 align-top text-sm";
  const numCell = cn(cell, "text-right whitespace-nowrap tabular-nums");

  return (
    <div className="hidden overflow-x-auto rounded-lg border border-border md:block">
      <table className="w-full min-w-max border-collapse">
        <caption className="sr-only">
          Order items{shipping ? ", with the quantity sent and still open" : ""}
        </caption>
        <thead className="bg-panel">
          <tr>
            <th scope="col" className={headCell}>
              #
            </th>
            <th scope="col" className={headCell}>
              Item
            </th>
            <th scope="col" className={numHead}>
              Ordered
            </th>
            {shipping ? (
              <>
                <th scope="col" className={numHead}>
                  Sent
                </th>
                <th scope="col" className={numHead}>
                  Open
                </th>
              </>
            ) : null}
            <th scope="col" className={numHead}>
              Rate
            </th>
            <th scope="col" className={numHead}>
              Discount
            </th>
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
            <tr key={line.id} className="border-t border-border">
              <td className={cn(cell, "text-muted-foreground tabular-nums")}>{line.lineNo}</td>
              <th scope="row" className={cn(cell, "min-w-56 text-left font-normal")}>
                <span className="block font-medium text-foreground">{line.description}</span>
                <span className="block text-xs text-muted-foreground">
                  HSN {line.hsnCode} · {line.uom}
                  {line.provisionalFields.length > 0 ? " · indicative" : ""}
                </span>
              </th>
              <td className={numCell}>{qty(line, line.qty)}</td>
              {shipping ? (
                <>
                  <td className={numCell}>{qty(line, line.qtyDispatched)}</td>
                  <td className={numCell}>
                    <span className={cn(Number(line.qtyOpen) > 0 && "font-medium")}>
                      {qty(line, line.qtyOpen)}
                    </span>
                    {Number(line.qtyShort) > 0 ? (
                      <span className="block text-xs text-muted-foreground">
                        {qty(line, line.qtyShort)} short
                      </span>
                    ) : null}
                  </td>
                </>
              ) : null}
              <td className={numCell}>{formatInr(line.rate, { paise: true })}</td>
              <td className={numCell}>{formatDiscount(line.discount)}</td>
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
  shipping,
}: {
  lines: readonly OrderLine[];
  intraState: boolean;
  shipping: boolean;
}): React.JSX.Element {
  return (
    <ol aria-label="Order items" className="flex flex-col gap-3 md:hidden">
      {lines.map((line) => (
        <li key={line.id} className="flex flex-col gap-2 rounded-lg border border-border p-3">
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
              {qty(line, line.qty)} {line.uom} × {formatInr(line.rate, { paise: true })}
            </dd>
            {shipping ? (
              <>
                <dt className="text-muted-foreground">Sent · open</dt>
                <dd className="text-right tabular-nums">
                  {qty(line, line.qtyDispatched)} · {qty(line, line.qtyOpen)}
                  {Number(line.qtyShort) > 0 ? ` (${qty(line, line.qtyShort)} short)` : ""}
                </dd>
              </>
            ) : null}
            <dt className="text-muted-foreground">Discount</dt>
            <dd className="text-right tabular-nums">{formatDiscount(line.discount)}</dd>
            <dt className="text-muted-foreground">Taxable</dt>
            <dd className="text-right tabular-nums">{formatInr(line.taxable, { paise: true })}</dd>
            <dt className="text-muted-foreground">GST {formatRate(line.gstSlab)}</dt>
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

function TotalsBlock({ order }: { order: Order }): React.JSX.Element {
  const { totals } = order;
  const rows: { label: string; value: string; strong?: boolean }[] = [
    { label: "Gross", value: formatInr(totals.gross, { paise: true }) },
    { label: "Discount", value: formatDiscount(totals.discount) },
    { label: "Taxable value", value: formatInr(totals.taxable, { paise: true }) },
    ...(order.intraState
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

/** Mirrors OrderDetailView block for block. */
export function OrderDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading sales order" className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-5 w-24" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-7 w-64" />
            <Skeleton className="h-6 w-28 rounded-full" />
          </div>
          <Skeleton className="h-5 w-56" />
        </div>
        <Skeleton className="h-control-md w-32 rounded-md" />
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
