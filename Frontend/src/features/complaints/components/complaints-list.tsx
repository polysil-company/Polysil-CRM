"use client";

import { Add01Icon, CustomerSupportIcon, Download04Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { FilterPill, SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Checkbox } from "@/components/ui/checkbox";
import { Icon } from "@/components/ui/icon";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { exportComplaints } from "@/features/complaints/api/complaints.api";
import {
  complaintListQueryOptions,
  complaintStatsQueryOptions,
} from "@/features/complaints/api/complaints.queries";
import {
  COMPLAINT_SEVERITIES,
  COMPLAINT_STATUSES,
  type ComplaintListParams,
  type ComplaintSummary,
} from "@/features/complaints/api/complaints.schemas";
import { useComplaintListParams } from "@/features/complaints/hooks/use-complaint-list-params";
import {
  COMPLAINT_STATUS_BADGE,
  COMPLAINT_STATUS_DESCRIPTIONS,
  COMPLAINT_STATUS_LABELS,
  SEVERITY_BADGE,
  SEVERITY_LABELS,
} from "@/features/complaints/lib/complaint-labels";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { saveFile } from "@/lib/api/save-file";
import { formatCount } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/complaints/components/complaints-list.tsx",
  dataId: "CMPL-001",
});

const SKELETON_ROWS = 5;

const STATUS_OPTIONS = COMPLAINT_STATUSES.map((value) => ({
  value,
  label: COMPLAINT_STATUS_LABELS[value],
  description: COMPLAINT_STATUS_DESCRIPTIONS[value],
}));
const SEVERITY_OPTIONS = COMPLAINT_SEVERITIES.map((value) => ({
  value,
  label: SEVERITY_LABELS[value],
}));

/**
 * CMPL-001 · Complaints: every one the user can see, newest first, filtered by search,
 * status, severity, type, late (a target missed) and no owner — or, for whoever checks or
 * tests them, "Waiting on me", oldest first. All of it is in the URL.
 */
export function ComplaintsList(): React.JSX.Element {
  const { view, params, activeFilterCount, setView, setFilters, resetFilters } =
    useComplaintListParams();
  const canCreate = useCan("complaints", "create");
  const decides = useCan("complaints", "approve");
  const types = useQuery(lookupListQueryOptions("complaint-types"));
  const typeOptions = (types.data ?? []).map((type) => ({ value: type.id, label: type.name }));

  return (
    <section aria-label="Complaints" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          {decides ? (
            <ToggleGroup
              aria-label="Which complaints"
              value={[view]}
              onValueChange={(next) => {
                const [choice] = next;
                if (choice === "all" || choice === "mine") setView(choice);
              }}
            >
              <ToggleGroupItem value="all">All</ToggleGroupItem>
              <ToggleGroupItem value="mine">Waiting on me</ToggleGroupItem>
            </ToggleGroup>
          ) : null}
          <ComplaintCounts />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {view === "all" ? <ExportComplaintsButton params={params} /> : null}
          {canCreate ? (
            <Link href="/complaints/new" className={buttonVariants()}>
              <Icon icon={Add01Icon} />
              New complaint
            </Link>
          ) : null}
        </div>
      </div>

      {view === "all" ? (
        <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
          <SearchField
            label="Search complaints"
            placeholder="Number, contact or mobile"
            value={params.q}
            onSearch={(q) => {
              setFilters({ q });
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <FilterPill
              label="Status"
              options={STATUS_OPTIONS}
              selected={params.status}
              onChange={(status) => {
                setFilters({ status });
              }}
            />
            <SingleFilterPill
              label="Severity"
              options={SEVERITY_OPTIONS}
              selected={params.severity}
              onChange={(severity) => {
                setFilters({ severity });
              }}
            />
            <SingleFilterPill
              label="Type"
              options={typeOptions}
              selected={params.typeId}
              emptyMessage={types.isPending ? "Loading types…" : "No types are set up yet."}
              onChange={(typeId) => {
                setFilters({ typeId });
              }}
            />
            <FlagFilter
              id="complaints-late"
              label="Late only"
              checked={params.breached}
              onChange={(breached) => {
                setFilters({ breached });
              }}
            />
            <FlagFilter
              id="complaints-unowned"
              label="No owner"
              checked={params.noOwner}
              onChange={(noOwner) => {
                setFilters({ noOwner });
              }}
            />
            {activeFilterCount > 0 ? (
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                Reset filters
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      <ComplaintRows
        params={params}
        filtered={activeFilterCount > 0}
        onReset={resetFilters}
        emptyMine={view === "mine"}
      />
    </section>
  );
}

/** CMPL-009 · The list as an Excel file, with the filters on screen. */
function ExportComplaintsButton({ params }: { params: ComplaintListParams }): React.JSX.Element {
  const download = useAsyncAction({
    action: () => exportComplaints(params),
    logger: log,
    fn: "handleExportComplaints",
    dataId: "CMPL-009",
    onSuccess: (file) => {
      saveFile(file, "complaints.xlsx");
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "export_too_large") {
        toast.error("Too many complaints to download", {
          description: "More than 5,000 match. Narrow the filters and try again.",
        });
        return;
      }
      const view = toUserFacingError(error);
      toast.error(view.title, { description: view.description });
    },
  });
  return (
    <Button
      variant="outline"
      state={download.state}
      loadingLabel="Preparing…"
      successLabel="Downloaded"
      errorLabel="Not downloaded"
      onClick={() => {
        void download.run();
      }}
    >
      <Icon icon={Download04Icon} />
      Download Excel
    </Button>
  );
}

function FlagFilter({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}): React.JSX.Element {
  return (
    <div className="flex items-center gap-2 px-1">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(next) => {
          onChange(next);
        }}
      />
      <Label htmlFor={id} className="text-sm">
        {label}
      </Label>
    </div>
  );
}

/** "3 waiting for a check · 2 with QC · 1 late", from GET /complaints/stats. */
function ComplaintCounts(): React.JSX.Element | null {
  const stats = useQuery(complaintStatsQueryOptions());
  if (stats.data === undefined) return null;
  const parts = [
    `${String(stats.data.byStatus.submitted ?? 0)} waiting for a check`,
    `${String(stats.data.byStatus.under_qc ?? 0)} with QC`,
  ];
  if (stats.data.breached > 0) parts.push(`${String(stats.data.breached)} late`);
  return <p className="text-sm text-muted-foreground">{parts.join(" · ")}</p>;
}

export interface ComplaintRowsProps {
  params: ComplaintListParams;
  filtered: boolean;
  onReset?: () => void;
  emptyMine?: boolean;
}

/** The rows for any set of filters: the list page, a lead's or an order's complaints. */
export function ComplaintRows({
  params,
  filtered,
  onReset,
  emptyMine = false,
}: ComplaintRowsProps): React.JSX.Element {
  const query = useInfiniteQuery(complaintListQueryOptions(params));
  const total = query.data?.pages[0]?.total ?? null;
  const capped = query.data?.pages[0]?.totalCapped ?? false;

  return (
    <QueryView
      query={query}
      pending={<ComplaintsListSkeleton />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={CustomerSupportIcon}
          title={
            emptyMine
              ? "Nothing waits on you"
              : filtered
                ? "No complaints match these filters"
                : "No complaints yet"
          }
          description={
            emptyMine
              ? "Complaints waiting for your check or your QC verdict appear here."
              : filtered
                ? "Change or reset the filters to see more."
                : "A complaint raised by staff or a dealer appears here once saved."
          }
          action={
            filtered && onReset !== undefined ? (
              <Button variant="outline" size="sm" onClick={onReset}>
                Reset filters
              </Button>
            ) : undefined
          }
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {total === null
              ? emptyMine
                ? "Oldest first."
                : "Newest first."
              : `${formatCount(total, { atLeast: capped })} ${total === 1 ? "complaint" : "complaints"}, ${emptyMine ? "oldest" : "newest"} first.`}
          </p>
          <ul aria-label="Complaints" className="flex flex-col gap-2">
            {data.pages.flatMap((page) =>
              page.items.map((complaint) => (
                <ComplaintRow key={complaint.id} complaint={complaint} />
              )),
            )}
          </ul>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The complaints above are still current.
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
                {query.isFetchNextPageError ? "Try again" : "Show more"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </QueryView>
  );
}

function ComplaintRow({ complaint }: { complaint: ComplaintSummary }): React.JSX.Element {
  const title = complaint.number ?? "Draft complaint";
  return (
    <li>
      <Link
        href={`/complaints/${complaint.id}`}
        aria-label={`${title}, ${complaint.contactName}, ${COMPLAINT_STATUS_LABELS[complaint.status]}${complaint.breached ? ", late" : ""}`}
        className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3 transition-colors duration-fast hover:bg-accent sm:p-4"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-foreground">{title}</span>
          <Badge variant={COMPLAINT_STATUS_BADGE[complaint.status]} dot>
            {COMPLAINT_STATUS_LABELS[complaint.status]}
          </Badge>
          <Badge variant={SEVERITY_BADGE[complaint.severity]}>
            {SEVERITY_LABELS[complaint.severity]}
          </Badge>
          {complaint.breached ? <Badge variant="danger">Late</Badge> : null}
          <span className="ml-auto text-xs text-muted-foreground">
            <RelativeDate value={complaint.firstSubmittedAt ?? complaint.createdAt} />
          </span>
        </div>
        <p className="truncate text-sm font-medium text-foreground">{complaint.contactName}</p>
        <p className="text-xs text-muted-foreground">
          {complaint.type.name}
          {complaint.partner?.name == null ? "" : ` · ${complaint.partner.name}`} ·{" "}
          {complaint.owner === null ? "No owner yet" : `Owner: ${complaint.owner.name}`}
        </p>
      </Link>
    </li>
  );
}

export function ComplaintsListSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading complaints" className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:p-4">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-56" />
        </div>
      ))}
    </div>
  );
}
