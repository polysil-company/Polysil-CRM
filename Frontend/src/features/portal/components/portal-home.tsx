"use client";

import { LinkSquare02Icon } from "@hugeicons/core-free-icons";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { StarRating } from "@/components/patterns/star-rating";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortalConsent } from "@/features/portal/api/portal.mutations";
import {
  portalComplaintsQueryOptions,
  portalEnquiriesQueryOptions,
  portalMeQueryOptions,
  portalOrdersQueryOptions,
  portalQuotationsQueryOptions,
  portalRatingsQueryOptions,
} from "@/features/portal/api/portal.queries";
import type { PortalMe, PortalRating } from "@/features/portal/api/portal.schemas";
import {
  complaintStatus,
  enquiryStatus,
  isPortalOff,
  orderStatus,
  quotationStatus,
  systemText,
} from "@/features/portal/lib/portal-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatCalendarDay, formatFullDate, formatIndianPhone, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { PortalRatingForm, type PortalRatingSubject } from "./portal-rating-form";

const log = createLogger({
  file: "features/portal/components/portal-home.tsx",
  dataId: "FARM-001",
});

/**
 * FARM-001 · A farmer's own record: their details and consent, their enquiries, quotations
 * (with the link they were sent), orders with their dispatches, and complaints. They can rate
 * an installation once it has shipped and a service once the complaint is closed (FARM-003).
 */
export function PortalHome(): React.JSX.Element {
  const me = useQuery(portalMeQueryOptions());

  if (me.status === "pending") return <PortalHomeSkeleton />;
  if (me.status === "error") {
    return isPortalOff(me.error) ? (
      <PortalOff />
    ) : (
      <ErrorState
        error={me.error}
        onRetry={() => {
          void me.refetch();
        }}
      />
    );
  }
  return <PortalRecord me={me.data} />;
}

function PortalOff(): React.JSX.Element {
  return (
    <Card>
      <CardHeader className="flex-col gap-1">
        <h1 className="text-lg font-semibold text-foreground">The portal is closed for now</h1>
        <CardDescription>
          Polysil has switched the farmers&apos; portal off. Your enquiries, orders and complaints
          are safe. Call your Polysil officer or dealer for an update.
        </CardDescription>
      </CardHeader>
    </Card>
  );
}

function PortalRecord({ me }: { me: PortalMe }): React.JSX.Element {
  const ratings = useQuery(portalRatingsQueryOptions());
  const [subject, setSubject] = useState<PortalRatingSubject | null>(null);
  /** Numbers the backend said can't be rated after all: their buttons go. */
  const [refused, setRefused] = useState<ReadonlySet<string>>(new Set());
  const rated = (subject: PortalRatingSubject): PortalRating | undefined =>
    ratings.data?.find((rating) =>
      subject.target === "installation"
        ? rating.target === "installation" && rating.orderNo === subject.orderNo
        : rating.target === "service" && rating.complaintNo === subject.complaintNo,
    );
  const rate = (next: PortalRatingSubject): (() => void) | null => {
    const key = next.target === "installation" ? next.orderNo : next.complaintNo;
    if (ratings.status !== "success" || refused.has(key)) return null;
    return () => {
      setSubject(next);
    };
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-foreground">Namaste, {me.name}</h1>
        <p className="text-sm text-muted-foreground tabular-nums">
          {formatIndianPhone(me.mobile)}
          {me.village === null ? "" : ` · ${me.village}`}
          {me.territoryName === null ? "" : ` · ${me.territoryName}`}
        </p>
      </div>

      <ConsentCard me={me} />

      <OrdersSection rated={rated} rate={rate} />
      <QuotationsSection />
      <ComplaintsSection rated={rated} rate={rate} />
      <EnquiriesSection />

      <Dialog
        open={subject !== null}
        onOpenChange={(next) => {
          if (!next) setSubject(null);
        }}
      >
        <DialogContent size="sm">
          {subject === null ? null : (
            <PortalRatingForm
              subject={subject}
              onDone={() => {
                setSubject(null);
              }}
              onRefused={() => {
                const key =
                  subject.target === "installation" ? subject.orderNo : subject.complaintNo;
                setRefused((before) => new Set([...before, key]));
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** FARM-002 · Whether Polysil may contact the farmer, which they switch themselves. */
function ConsentCard({ me }: { me: PortalMe }): React.JSX.Element {
  const given = me.consentGivenAt !== null;
  const mutation = usePortalConsent();
  const idempotency = useIdempotencyKey();
  const save = useAsyncAction({
    action: () =>
      mutation.mutateAsync({
        consentGiven: !given,
        idempotencyKey: idempotency.keyFor({ consentGiven: !given }),
      }),
    logger: log,
    fn: given ? "handleWithdrawConsent" : "handleGiveConsent",
    dataId: "FARM-002",
    onSuccess: () => {
      idempotency.reset();
      toast.success(given ? "You won't be contacted" : "Thank you, we may contact you");
    },
    onError: (error) => {
      toast.error("That didn't save", { description: toUserFacingError(error).description });
    },
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-sm font-medium text-foreground">Updates from Polysil</h2>
          <p className="text-sm text-muted-foreground">
            {given && me.consentGivenAt !== null
              ? `You agreed to be contacted on ${formatFullDate(me.consentGivenAt)}.`
              : "You haven't agreed to be contacted about offers and updates."}
          </p>
        </div>
        <Button
          variant={given ? "outline" : "primary"}
          aria-pressed={given}
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
          className="w-full sm:w-auto"
          onClick={() => {
            void save.run();
          }}
        >
          {given ? "Stop updates" : "Yes, contact me"}
        </Button>
      </CardContent>
    </Card>
  );
}

/** A titled list with its own loading, empty and error states. */
function Section<TItem>({
  title,
  description,
  query,
  empty,
  children,
}: {
  title: string;
  description?: string;
  query: UseQueryResult<TItem[]>;
  empty: string;
  children: (items: TItem[]) => React.ReactNode;
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader className="flex-col gap-0.5">
        <CardTitle level={2} className="flex items-center gap-2 text-base">
          {title}
          {query.status === "success" ? (
            <span className="text-sm font-normal text-muted-foreground tabular-nums">
              {query.data.length}
            </span>
          ) : null}
        </CardTitle>
        {description === undefined ? null : <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        {query.status === "pending" ? (
          <div
            aria-busy="true"
            aria-label={`Loading ${title.toLowerCase()}`}
            className="flex flex-col gap-2"
          >
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : query.status === "error" ? (
          isPortalOff(query.error) ? (
            <p className="text-sm text-muted-foreground">The portal is closed for now.</p>
          ) : (
            <ErrorState
              error={query.error}
              onRetry={() => {
                void query.refetch();
              }}
            />
          )
        ) : query.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul aria-label={title} className="flex flex-col divide-y divide-border">
            {children(query.data)}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Row({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between">
      {children}
    </li>
  );
}

/** "You rated 4 stars", or what an officer recorded for him, or the button to rate. */
function RatingSlot({
  rating,
  onRate,
  label,
}: {
  rating: PortalRating | undefined;
  onRate: (() => void) | null;
  label: string;
}): React.JSX.Element | null {
  if (rating !== undefined) {
    return (
      <span className="flex items-center gap-2 text-xs text-muted-foreground">
        <StarRating score={rating.score} size="xs" />
        {rating.enteredVia === "portal" ? "Your rating" : "Rated with our officer"}
      </span>
    );
  }
  if (onRate === null) return null;
  return (
    <Button variant="outline" size="sm" aria-label={label} onClick={onRate}>
      Rate
    </Button>
  );
}

function OrdersSection({
  rated,
  rate,
}: {
  rated: (subject: PortalRatingSubject) => PortalRating | undefined;
  rate: (subject: PortalRatingSubject) => (() => void) | null;
}): React.JSX.Element {
  const query = useQuery(portalOrdersQueryOptions());
  return (
    <Section
      title="Your orders"
      description="Rate the installation once something has been dispatched."
      query={query}
      empty="No orders yet."
    >
      {(orders) =>
        orders.map((order) => {
          const status = orderStatus(order.status);
          const subject: PortalRatingSubject = { target: "installation", orderNo: order.number };
          return (
            <Row key={order.number}>
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-medium text-foreground">
                    {order.number}
                  </span>
                  <Badge variant={status.tone} size="sm">
                    {status.label}
                  </Badge>
                </div>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {order.total === null ? "Through your dealer" : formatInr(order.total)}
                  {order.submittedAt === null
                    ? ""
                    : ` · placed ${formatFullDate(order.submittedAt)}`}
                </span>
                {order.dispatches.length === 0 ? null : (
                  <ul
                    aria-label={`Dispatches of ${order.number}`}
                    className="flex flex-col gap-0.5"
                  >
                    {order.dispatches.map((dispatch) => (
                      <li
                        key={`${dispatch.dcNo ?? ""}-${dispatch.dispatchedAt}`}
                        className="text-xs text-foreground tabular-nums"
                      >
                        Dispatched {formatFullDate(dispatch.dispatchedAt)}
                        {dispatch.dcNo === null ? "" : ` · challan ${dispatch.dcNo}`}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {order.dispatches.length === 0 ? null : (
                <RatingSlot
                  rating={rated(subject)}
                  onRate={rate(subject)}
                  label={`Rate the installation of ${order.number}`}
                />
              )}
            </Row>
          );
        })
      }
    </Section>
  );
}

function QuotationsSection(): React.JSX.Element {
  const query = useQuery(portalQuotationsQueryOptions());
  return (
    <Section title="Your quotations" query={query} empty="No quotations yet.">
      {(quotations) =>
        quotations.map((quotation, index) => {
          const status = quotationStatus(quotation.status);
          return (
            <Row key={quotation.number ?? `quotation-${String(index)}`}>
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-medium text-foreground">
                    {quotation.number ?? "Quotation"}
                  </span>
                  <Badge variant={status.tone} size="sm">
                    {status.label}
                  </Badge>
                </div>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {quotation.total === null ? "Through your dealer" : formatInr(quotation.total)}
                  {quotation.sentAt === null ? "" : ` · sent ${formatFullDate(quotation.sentAt)}`}
                  {quotation.validUntil === null
                    ? ""
                    : ` · valid until ${formatCalendarDay(quotation.validUntil)}`}
                </span>
              </div>
              {quotation.link === null ? null : (
                <a
                  href={quotation.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  Open
                  <Icon icon={LinkSquare02Icon} size="sm" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              )}
            </Row>
          );
        })
      }
    </Section>
  );
}

function ComplaintsSection({
  rated,
  rate,
}: {
  rated: (subject: PortalRatingSubject) => PortalRating | undefined;
  rate: (subject: PortalRatingSubject) => (() => void) | null;
}): React.JSX.Element {
  const query = useQuery(portalComplaintsQueryOptions());
  return (
    <Section
      title="Your complaints"
      description="Rate how we handled it once a complaint is closed."
      query={query}
      empty="No complaints. We're glad."
    >
      {(complaints) =>
        complaints.map((complaint) => {
          const status = complaintStatus(complaint.status);
          const subject: PortalRatingSubject = { target: "service", complaintNo: complaint.number };
          return (
            <Row key={complaint.number}>
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-medium text-foreground">
                    {complaint.number}
                  </span>
                  <Badge variant={status.tone} size="sm">
                    {status.label}
                  </Badge>
                </div>
                {complaint.raisedAt === null ? null : (
                  <span className="text-xs text-muted-foreground">
                    Raised {formatFullDate(complaint.raisedAt)}
                  </span>
                )}
              </div>
              {complaint.status === "closed" ? (
                <RatingSlot
                  rating={rated(subject)}
                  onRate={rate(subject)}
                  label={`Rate the service on ${complaint.number}`}
                />
              ) : null}
            </Row>
          );
        })
      }
    </Section>
  );
}

function EnquiriesSection(): React.JSX.Element {
  const query = useQuery(portalEnquiriesQueryOptions());
  return (
    <Section title="Your enquiries" query={query} empty="No enquiries yet.">
      {(enquiries) =>
        enquiries.map((enquiry) => {
          const status = enquiryStatus(enquiry.status);
          return (
            <Row key={enquiry.code}>
              <div className="flex min-w-0 flex-col gap-1">
                <span className="font-mono text-sm font-medium text-foreground">
                  {enquiry.code}
                </span>
                <span className="text-xs text-muted-foreground">
                  {systemText(enquiry.system)} · {formatFullDate(enquiry.createdAt)}
                </span>
              </div>
              <Badge variant={status.tone} size="sm" className="self-start">
                {status.label}
              </Badge>
            </Row>
          );
        })
      }
    </Section>
  );
}

export function PortalHomeSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading your record" className="flex flex-col gap-5">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-20 w-full rounded-xl" />
      <Skeleton className="h-40 w-full rounded-xl" />
      <Skeleton className="h-40 w-full rounded-xl" />
    </div>
  );
}
