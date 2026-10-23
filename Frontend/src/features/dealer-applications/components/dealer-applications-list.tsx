"use client";

import { Add01Icon, UserAdd01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { dealerApplicationListQueryOptions } from "@/features/dealer-applications/api/dealer-applications.queries";
import {
  DEALER_APPLICATION_STATUSES,
  type DealerApplicationListParams,
  type DealerApplicationRow,
} from "@/features/dealer-applications/api/dealer-applications.schemas";
import {
  DEALER_APPLICATION_STATUS_BADGE,
  DEALER_APPLICATION_STATUS_LABELS,
} from "@/features/dealer-applications/lib/dealer-application-labels";
import { useCan } from "@/features/session/hooks/use-session";

import { StartDealerApplication } from "./start-dealer-application";

const SKELETON_ROWS = 4;

const STATUS_OPTIONS = DEALER_APPLICATION_STATUSES.map((value) => ({
  value,
  label: DEALER_APPLICATION_STATUS_LABELS[value],
}));

/** CHNL-007 · The list's filters, in the URL: one status and a search. */
function useListParams(): {
  params: DealerApplicationListParams;
  status: (typeof DEALER_APPLICATION_STATUSES)[number] | null;
  filtered: boolean;
  setStatus: (status: (typeof DEALER_APPLICATION_STATUSES)[number] | null) => void;
  setQ: (q: string) => void;
  reset: () => void;
} {
  const [values, setValues] = useQueryStates({
    q: parseAsString.withDefault(""),
    status: parseAsStringLiteral(DEALER_APPLICATION_STATUSES),
  });
  const q = values.q.trim();
  return {
    params: { q, status: values.status === null ? [] : [values.status] },
    status: values.status,
    filtered: q !== "" || values.status !== null,
    setStatus: (status) => {
      void setValues({ status });
    },
    setQ: (next) => {
      void setValues({ q: next === "" ? null : next });
    },
    reset: () => {
      void setValues({ q: null, status: null });
    },
  };
}

/**
 * CHNL-007 · Dealer applications (FS-053): newest first, with the firm, whom to ask for, the
 * area and where each stands; filtered by status and a search on firm, contact or mobile.
 * Staff who see partners start one, and send the applicant its link.
 */
export function DealerApplicationsList(): React.JSX.Element {
  const { params, status, filtered, setStatus, setQ, reset } = useListParams();
  const canView = useCan("partners", "view");
  const [starting, setStarting] = useState(false);
  const query = useQuery(dealerApplicationListQueryOptions(params));

  return (
    <section aria-label="Dealer applications" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">
          A prospective dealer fills in the firm&apos;s details from a link, and a State Manager or
          above approves it. Approving adds the dealer and its login.
        </p>
        {canView ? (
          <Button
            onClick={() => {
              setStarting(true);
            }}
          >
            <Icon icon={Add01Icon} />
            Start an application
          </Button>
        ) : null}
      </div>

      <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Search applications"
          placeholder="Firm, contact or mobile"
          value={params.q}
          onSearch={setQ}
        />
        <div className="flex flex-wrap items-center gap-2">
          <SingleFilterPill
            label="Status"
            options={STATUS_OPTIONS}
            selected={status}
            onChange={setStatus}
          />
          {filtered ? (
            <Button variant="ghost" size="sm" onClick={reset}>
              Reset filters
            </Button>
          ) : null}
        </div>
      </div>

      <QueryView
        query={query}
        pending={<DealerApplicationsSkeleton />}
        isEmpty={(rows) => rows.length === 0}
        empty={
          <EmptyState
            icon={UserAdd01Icon}
            title={filtered ? "No application matches these filters" : "No dealer applications yet"}
            description={
              filtered
                ? "Change or reset the filters to see more."
                : "Start one here, or win a dealership lead: either sends the applicant a link."
            }
            action={
              filtered ? (
                <Button variant="outline" size="sm" onClick={reset}>
                  Reset filters
                </Button>
              ) : undefined
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(rows) => (
          <ul aria-label="Dealer applications" className="flex flex-col gap-2">
            {rows.map((row) => (
              <ApplicationRow key={row.id} row={row} />
            ))}
          </ul>
        )}
      </QueryView>

      <Dialog open={starting} onOpenChange={setStarting}>
        <DialogContent size="sm">
          {starting ? (
            <StartDealerApplication
              onClose={() => {
                setStarting(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function ApplicationRow({ row }: { row: DealerApplicationRow }): React.JSX.Element {
  const label = DEALER_APPLICATION_STATUS_LABELS[row.status];
  return (
    <li>
      <Link
        href={`/partners/applications/${row.id}`}
        transitionTypes={["nav-forward"]}
        aria-label={`${row.firmName}, ${row.contactName}, ${label}`}
        className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3 transition-colors duration-fast hover:bg-accent sm:p-4"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{row.firmName}</span>
          <Badge variant={DEALER_APPLICATION_STATUS_BADGE[row.status]} dot>
            {label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {row.contactName} · {row.territoryName} ·{" "}
          {row.submittedAt === null ? (
            <>
              started <RelativeDate value={row.createdAt} />
            </>
          ) : (
            <>
              submitted <RelativeDate value={row.submittedAt} />
            </>
          )}
        </p>
      </Link>
    </li>
  );
}

export function DealerApplicationsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading applications" className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:p-4">
          <Skeleton className="h-4 w-56" />
          <Skeleton className="h-3 w-72" />
        </div>
      ))}
    </div>
  );
}
