"use client";

import {
  ArrowLeft01Icon,
  Clock01Icon,
  Edit02Icon,
  UserCircleIcon,
} from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import {
  customerDetailQueryOptions,
  customerTimelineQueryOptions,
} from "@/features/customers/api/customers.queries";
import type {
  CustomerDetail as CustomerDetailData,
  CustomerTimelineEvent,
} from "@/features/customers/api/customers.schemas";
import {
  CONSENT_CHANNEL_LABELS,
  CUSTOMER_TYPE_LABELS,
} from "@/features/customers/lib/customer-labels";
import { LEAD_STAGES } from "@/features/leads/api/leads.schemas";
import { LeadStageBadge } from "@/features/leads/components/lead-stage-badge";
import { TimelineItem } from "@/features/leads/components/lead-timeline";
import { LookupName } from "@/features/lookups/components/lookup-name";
import { ORDER_STATUSES } from "@/features/orders/api/orders.schemas";
import { OrderStatusBadge } from "@/features/orders/components/order-status-badge";
import { QUOTATION_STATUSES } from "@/features/quotations/api/quotations.schemas";
import {
  QUOTATION_STATUS_BADGE,
  QUOTATION_STATUS_LABELS,
} from "@/features/quotations/lib/quotation-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { EMPTY_VALUE, formatFullDate, formatIndianPhone, formatInr } from "@/lib/format";

import { ConsentForm } from "./consent-dialog";
import { CustomerEditForm } from "./customer-edit-dialog";

/**
 * LEAD-017 · A customer: the details with Edit and consent (LEAD-018, staff with leads edit),
 * its leads with their source and campaign, its quotations and orders, and the timeline across
 * them. Only what the user can see; 404 when they can see none of its leads.
 */
export function CustomerDetail({ customerId }: { customerId: string }): React.JSX.Element {
  const query = useQuery(customerDetailQueryOptions(customerId));
  if (query.status === "error" && isApiError(query.error) && query.error.status === 404) {
    notFound();
  }
  return (
    <QueryView
      query={query}
      pending={<CustomerDetailSkeleton />}
      isEmpty={() => false}
      empty={null}
    >
      {(customer) => <CustomerView customer={customer} />}
    </QueryView>
  );
}

function CustomerView({ customer }: { customer: CustomerDetailData }): React.JSX.Element {
  const staff = useIsStaff();
  const mayEditLeads = useCan("leads", "edit");
  const canEdit = staff && mayEditLeads;
  const [open, setOpen] = useState<"edit" | "consent" | null>(null);
  const codeOf = (leadId: string): string =>
    customer.leads.find((lead) => lead.id === leadId)?.code ?? "a lead";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Link
          href="/customers"
          transitionTypes={["nav-back"]}
          className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
        >
          <Icon icon={ArrowLeft01Icon} size="sm" />
          All customers
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-semibold text-foreground">{customer.name}</h2>
          <Badge variant="outline">{CUSTOMER_TYPE_LABELS[customer.type]}</Badge>
          {customer.consentGivenAt === null ? (
            <Badge variant="neutral">No consent</Badge>
          ) : (
            <Badge variant="success">Consent given</Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground tabular-nums">
          {formatIndianPhone(customer.mobile)}
          {customer.territory === null ? "" : ` · ${customer.territory.name}`} ·{" "}
          {customer.leadCount === 1 ? "1 lead" : `${String(customer.leadCount)} leads`}
        </p>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <RelatedCard title="Leads" count={customer.leads.length} empty="No leads you can see.">
            {customer.leads.map((lead) => (
              <li
                key={lead.id}
                className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex min-w-0 flex-col gap-0.5">
                  <Link
                    href={`/leads/${lead.id}`}
                    className="font-mono text-sm font-medium text-primary-text underline-offset-4 hover:underline"
                  >
                    {lead.code}
                  </Link>
                  <span className="text-xs text-muted-foreground">
                    <LookupName list="lead-sources" code={lead.source} />
                    {lead.campaignName === null ? "" : ` · ${lead.campaignName}`} ·{" "}
                    {formatFullDate(lead.createdAt)}
                  </span>
                </div>
                {LEAD_STAGES.some((stage) => stage === lead.stage) ? (
                  <LeadStageBadge
                    stage={LEAD_STAGES.find((stage) => stage === lead.stage) ?? "new"}
                  />
                ) : (
                  <Badge variant="outline">{lead.stage}</Badge>
                )}
              </li>
            ))}
          </RelatedCard>
          <RelatedCard
            title="Quotations"
            count={customer.quotations.length}
            empty="No quotations on these leads."
          >
            {customer.quotations.map((quotation) => {
              const status = QUOTATION_STATUSES.find((item) => item === quotation.status);
              return (
                <li
                  key={quotation.id}
                  className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <Link
                      href={`/quotations/${quotation.id}`}
                      className="font-mono text-sm font-medium text-primary-text underline-offset-4 hover:underline"
                    >
                      {quotation.quoteNo ?? "Draft quotation"}
                    </Link>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatInr(quotation.total, { paise: true })} · on {codeOf(quotation.leadId)}
                      {quotation.sentAt === null
                        ? ""
                        : ` · sent ${formatFullDate(quotation.sentAt)}`}
                    </span>
                  </div>
                  {status === undefined ? (
                    <Badge variant="outline">{quotation.status}</Badge>
                  ) : (
                    <Badge variant={QUOTATION_STATUS_BADGE[status]} dot>
                      {QUOTATION_STATUS_LABELS[status]}
                    </Badge>
                  )}
                </li>
              );
            })}
          </RelatedCard>
          <RelatedCard
            title="Orders"
            count={customer.orders.length}
            empty="No orders on these leads."
          >
            {customer.orders.map((order) => {
              const status = ORDER_STATUSES.find((item) => item === order.status);
              return (
                <li
                  key={order.id}
                  className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <Link
                      href={`/sales-orders/${order.id}`}
                      className="font-mono text-sm font-medium text-primary-text underline-offset-4 hover:underline"
                    >
                      {order.orderNo ?? "Draft order"}
                    </Link>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatInr(order.total, { paise: true })} · on {codeOf(order.leadId)}
                      {order.submittedAt === null
                        ? ""
                        : ` · submitted ${formatFullDate(order.submittedAt)}`}
                    </span>
                  </div>
                  {status === undefined ? (
                    <Badge variant="outline">{order.status}</Badge>
                  ) : (
                    <OrderStatusBadge status={status} />
                  )}
                </li>
              );
            })}
          </RelatedCard>
          <Card>
            <CardHeader>
              <CardTitle level={3}>Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <CustomerTimeline customerId={customer.id} />
            </CardContent>
          </Card>
        </div>

        <Card className="lg:sticky lg:top-4">
          <CardHeader className="flex-wrap">
            <CardTitle level={3}>Details</CardTitle>
            {canEdit ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setOpen("edit");
                }}
              >
                <Icon icon={Edit02Icon} />
                Edit
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3">
              <Item label="Mobile">{formatIndianPhone(customer.mobile)}</Item>
              <Item label="Email">{customer.email ?? EMPTY_VALUE}</Item>
              <Item label="Area">
                {customer.territory === null ? EMPTY_VALUE : customer.territory.name}
              </Item>
              <Item label="Village">{customer.village ?? EMPTY_VALUE}</Item>
              <Item label="Address">{customer.address ?? EMPTY_VALUE}</Item>
              <Item label="Survey no.">{customer.surveyNo ?? EMPTY_VALUE}</Item>
              <Item label="Consent">
                {customer.consentGivenAt === null ? (
                  "Not given"
                ) : (
                  <>
                    Given {formatFullDate(customer.consentGivenAt)}
                    {customer.consentChannel === null ? null : (
                      <span className="block text-xs text-muted-foreground">
                        {CONSENT_CHANNEL_LABELS[customer.consentChannel]}
                      </span>
                    )}
                  </>
                )}
              </Item>
              <Item label="Customer since">{formatFullDate(customer.createdAt)}</Item>
            </dl>
            {canEdit ? (
              <Button
                variant="outline"
                size="sm"
                className="mt-4 w-full"
                onClick={() => {
                  setOpen("consent");
                }}
              >
                {customer.consentGivenAt === null ? "Record consent" : "Withdraw consent"}
              </Button>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={open !== null}
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
      >
        <DialogContent size={open === "edit" ? "md" : "sm"}>
          {open === "edit" ? (
            <CustomerEditForm
              customer={customer}
              onDone={() => {
                setOpen(null);
              }}
            />
          ) : open === "consent" ? (
            <ConsentForm
              customer={customer}
              onDone={() => {
                setOpen(null);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Item({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm text-foreground">{children}</dd>
    </div>
  );
}

function RelatedCard({
  title,
  count,
  empty,
  children,
}: {
  title: string;
  count: number;
  empty: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle level={3} className="flex items-center gap-2">
          {title}
          <span className="text-sm font-normal text-muted-foreground tabular-nums">{count}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {count === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul aria-label={title} className="flex flex-col divide-y divide-border">
            {children}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** What the customer's own events say; a lead's entries read as on the lead's own timeline. */
function customerEventText(event: CustomerTimelineEvent): string {
  switch (event.kind) {
    case "customer.created":
      return "became a customer";
    case "customer.updated":
      return event.payload.consent_given === true
        ? "recorded the customer's consent"
        : event.payload.consent_given === false
          ? "withdrew the customer's consent"
          : "updated the customer's details";
    default:
      return event.kind.replace(/^customer\./, "").replace(/_/g, " ");
  }
}

/** An entry with nobody behind it reads on its own: "Became a customer". */
function sentenceCase(text: string): string {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

/**
 * LEAD-017 · Everything on the customer's leads, and to the customer, newest first. Each lead
 * entry names the lead it happened on.
 */
function CustomerTimeline({ customerId }: { customerId: string }): React.JSX.Element {
  const query = useInfiniteQuery(customerTimelineQueryOptions(customerId));
  return (
    <QueryView
      query={query}
      pending={
        <div aria-busy="true" aria-label="Loading the timeline" className="flex flex-col gap-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      }
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={Clock01Icon}
          title="Nothing yet"
          description="What happens on this customer's leads shows here."
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-4">
          <ol aria-label="Customer timeline, newest first" className="flex flex-col">
            {data.pages.flatMap((page) =>
              page.items.map((event) =>
                event.leadId === null ? (
                  <li key={event.id} className="flex gap-3 pb-5 last:pb-0">
                    <span
                      aria-hidden="true"
                      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary-text"
                    >
                      <Icon icon={UserCircleIcon} size="md" />
                    </span>
                    <div className="flex min-w-0 flex-1 flex-col gap-1 pt-1">
                      <p className="text-sm text-foreground">
                        {event.actor?.name == null ? (
                          sentenceCase(customerEventText(event))
                        ) : (
                          <>
                            <span className="font-medium">{event.actor.name}</span>{" "}
                            {customerEventText(event)}
                          </>
                        )}
                      </p>
                      <RelativeDate
                        value={event.occurredAt}
                        className="text-xs text-muted-foreground"
                      />
                    </div>
                  </li>
                ) : (
                  <TimelineItem
                    key={event.id}
                    event={event}
                    leadId={event.leadId}
                    on={
                      <Link
                        href={`/leads/${event.leadId}`}
                        className="font-mono underline-offset-2 hover:text-foreground hover:underline"
                      >
                        {event.leadCode ?? "the lead"}
                      </Link>
                    }
                  />
                ),
              ),
            )}
          </ol>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2 pl-11">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The timeline above is still current.
                </p>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                state={query.isFetchingNextPage ? "loading" : "idle"}
                loadingLabel="Loading…"
                onClick={() => {
                  void query.fetchNextPage();
                }}
              >
                {query.isFetchNextPageError ? "Try again" : "Show older"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </QueryView>
  );
}

export function CustomerDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the customer" className="flex flex-col gap-5">
      <Skeleton className="h-7 w-64" />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-32 w-full rounded-xl" />
        </div>
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    </div>
  );
}
