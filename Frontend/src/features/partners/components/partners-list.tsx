"use client";

import { Add01Icon, Cancel01Icon, FileImportIcon, Store01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { ImportDialog } from "@/features/imports/components/import-dialog";
import { exportPartners } from "@/features/partners/api/partners.api";
import {
  partnerDetailQueryOptions,
  partnerKeys,
  partnerListQueryOptions,
} from "@/features/partners/api/partners.queries";
import {
  PARTNER_TYPES,
  type Partner,
  type PartnerListParams,
} from "@/features/partners/api/partners.schemas";
import {
  PARTNER_STATUSES,
  usePartnerListParams,
} from "@/features/partners/hooks/use-partner-list-params";
import { PARTNER_TYPE_LABELS } from "@/features/partners/lib/partner-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { mobileText } from "@/features/users/lib/user-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatCount } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/partners/components/partners-list.tsx",
  dataId: "CHNL-001",
});

const SKELETON_ROWS = 6;

const TYPE_OPTIONS = PARTNER_TYPES.map((value) => ({ value, label: PARTNER_TYPE_LABELS[value] }));
const STATUS_OPTIONS = [
  ...PARTNER_STATUSES.map((value) => ({
    value,
    label: value === "open" ? "Open" : "Closed",
  })),
  { value: "all" as const, label: "Open and closed" },
];

/**
 * CHNL-001 · Channel partners in the caller's scope, newest first: searched by name, code or
 * contact person, filtered by type, open or closed and the partner they sit under — all in
 * the URL. Whoever may add partners gets "New partner" and, on staff, the Excel import
 * (CHNL-005); the list downloads as Excel with the filters on screen.
 */
export function PartnersList(): React.JSX.Element {
  const { params, status, activeFilterCount, setFilters, resetFilters } = usePartnerListParams();
  const canCreate = useCan("partners", "create");
  // Partner and price imports are staff only (imports.md), whatever the permissions say.
  const staff = useIsStaff();
  const [importing, setImporting] = useState(false);
  const queryClient = useQueryClient();

  return (
    <section aria-label="Channel partners" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <SearchField
          label="Search partners"
          placeholder="Name, code or contact person"
          value={params.q}
          onSearch={(q) => {
            setFilters({ q });
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <DownloadExcelButton
            download={() => exportPartners({ ...params, cursor: null })}
            fallbackName="partners.xlsx"
            what="partners"
            logger={log}
            dataId="CHNL-001"
          />
          {canCreate && staff ? (
            <Button
              variant="outline"
              onClick={() => {
                setImporting(true);
              }}
            >
              <Icon icon={FileImportIcon} />
              Import from Excel
            </Button>
          ) : null}
          {canCreate ? (
            <Link href="/partners/new" className={buttonVariants()}>
              <Icon icon={Add01Icon} />
              New partner
            </Link>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SingleFilterPill
          label="Type"
          options={TYPE_OPTIONS}
          selected={params.type}
          onChange={(type) => {
            setFilters({ type });
          }}
        />
        <SingleFilterPill
          label="Status"
          options={STATUS_OPTIONS}
          selected={status}
          onChange={(next) => {
            setFilters({ status: next ?? "open" });
          }}
        />
        {params.parentId === null ? null : (
          <ParentChip
            parentId={params.parentId}
            onClear={() => {
              setFilters({ parentId: null });
            }}
          />
        )}
        {activeFilterCount > 0 ? (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Reset filters
          </Button>
        ) : null}
      </div>

      <PartnerRows
        params={params}
        filtered={activeFilterCount > 0}
        canCreate={canCreate}
        onReset={resetFilters}
      />

      {canCreate && staff ? (
        <ImportDialog
          kind="partners"
          open={importing}
          onOpenChange={setImporting}
          title="Import partners from Excel"
          description="Distributors, dealers and sub-dealers from a sheet: a dealer names its distributor's code, which may be a row in the same file."
          noun={{ one: "partner", many: "partners" }}
          onCommitted={(result) => {
            void queryClient.invalidateQueries({ queryKey: partnerKeys.all });
            toast.success(
              `${formatCount(result.created)} partner${result.created === 1 ? "" : "s"} added`,
            );
          }}
        />
      ) : null}
    </section>
  );
}

/** "Under Saurashtra Agro Distributors ×": the parent filter, named from its own record. */
function ParentChip({
  parentId,
  onClear,
}: {
  parentId: string;
  onClear: () => void;
}): React.JSX.Element {
  const parent = useQuery(partnerDetailQueryOptions(parentId));
  const name = parent.data?.name ?? (parent.isError ? "a partner" : "…");
  return (
    <Badge variant="info" className="gap-1 pr-1">
      Under {name}
      <button
        type="button"
        aria-label={`Show partners under any partner, not only ${name}`}
        className="rounded-full p-0.5 hover:bg-accent"
        onClick={onClear}
      >
        <Icon icon={Cancel01Icon} size="sm" />
      </button>
    </Badge>
  );
}

function PartnerRows({
  params,
  filtered,
  canCreate,
  onReset,
}: {
  params: Omit<PartnerListParams, "cursor">;
  filtered: boolean;
  canCreate: boolean;
  onReset: () => void;
}): React.JSX.Element {
  const query = useInfiniteQuery(partnerListQueryOptions(params));
  const total = query.data?.pages[0]?.total ?? null;
  const capped = query.data?.pages[0]?.totalCapped ?? false;

  return (
    <QueryView
      query={query}
      pending={<PartnersListSkeleton />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={Store01Icon}
          title={filtered ? "No partner matches these filters" : "No channel partners yet"}
          description={
            filtered
              ? "Change or reset the filters to see more."
              : canCreate
                ? "Add a distributor first; its dealers and their sub-dealers go under it."
                : "Partners in your area appear here once they're added."
          }
          action={
            filtered ? (
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
              ? "Newest first."
              : `${formatCount(total, { atLeast: capped })} ${total === 1 ? "partner" : "partners"}, newest first.`}
          </p>
          <ul aria-label="Partners" className="flex flex-col gap-2">
            {data.pages.flatMap((page) =>
              page.items.map((partner) => <PartnerListRow key={partner.id} partner={partner} />),
            )}
          </ul>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The partners above are still current.
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

function PartnerListRow({ partner }: { partner: Partner }): React.JSX.Element {
  const type = PARTNER_TYPE_LABELS[partner.type];
  const place = partner.territory?.name ?? "No territory";
  const contact = [partner.contactName, mobileText(partner.mobile)]
    .filter((part) => part !== null && part !== "")
    .join(" · ");
  return (
    <li>
      <Link
        href={`/partners/${partner.id}`}
        aria-label={`${partner.name}, ${type}, ${partner.code}${partner.active ? "" : ", closed"}`}
        className="flex flex-col gap-1 rounded-xl border border-border bg-card p-3 transition-colors duration-fast hover:bg-accent sm:flex-row sm:items-center sm:gap-4 sm:p-4"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-foreground">{partner.name}</span>
            <Badge variant="neutral">{type}</Badge>
            {partner.active ? null : <Badge variant="neutral">Closed</Badge>}
          </div>
          <span className="truncate text-xs text-muted-foreground">
            {partner.code}
            {partner.parent === null ? "" : ` · under ${partner.parent.name}`}
          </span>
        </div>
        <div className="flex min-w-0 flex-col gap-0.5 sm:w-56">
          <span className="truncate text-sm text-foreground">{place}</span>
          <span className="truncate text-xs text-muted-foreground">
            {contact === "" ? "No contact recorded" : contact}
          </span>
        </div>
        <span className="text-xs text-muted-foreground sm:w-28 sm:text-right">
          {partner.users === 0
            ? "No users"
            : `${String(partner.users)} user${partner.users === 1 ? "" : "s"}`}
        </span>
      </Link>
    </li>
  );
}

export function PartnersListSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading partners" className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 rounded-xl border border-border p-3 sm:p-4"
        >
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-3 w-40" />
          </div>
          <Skeleton className="hidden h-4 w-40 sm:block" />
          <Skeleton className="hidden h-4 w-16 sm:block" />
        </div>
      ))}
    </div>
  );
}
