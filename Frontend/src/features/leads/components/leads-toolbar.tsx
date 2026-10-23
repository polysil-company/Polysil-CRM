"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { FilterPill, SingleFilterPill } from "@/components/patterns/filter-pill";
import { Notice } from "@/components/patterns/notice";
import { SearchField } from "@/components/patterns/search-field";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Skeleton } from "@/components/ui/skeleton";
import { activeCampaignsQueryOptions } from "@/features/campaigns/api/campaigns.queries";
import { exportLeads } from "@/features/leads/api/leads.api";
import { LEAD_INQUIRY_TYPES, LEAD_STAGES } from "@/features/leads/api/leads.schemas";
import { useLeadListParams } from "@/features/leads/hooks/use-lead-list-params";
import {
  LEAD_INQUIRY_TYPE_LABELS,
  LEAD_STAGE_DESCRIPTIONS,
  LEAD_STAGE_LABELS,
} from "@/features/leads/lib/lead-labels";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { createLogger } from "@/lib/logger";

import { LeadAreaFilter } from "./lead-area-filter";
import { NewLeadDialog } from "./new-lead-dialog";

const log = createLogger({
  file: "features/leads/components/leads-toolbar.tsx",
  dataId: "LEAD-001",
});

const STAGE_OPTIONS = LEAD_STAGES.map((stage) => ({
  value: stage,
  label: LEAD_STAGE_LABELS[stage],
  description: LEAD_STAGE_DESCRIPTIONS[stage],
}));
const TYPE_OPTIONS = LEAD_INQUIRY_TYPES.map((type) => ({
  value: type,
  label: LEAD_INQUIRY_TYPE_LABELS[type],
}));

/** What the Source pill says when it has no options: three different reasons, three messages. */
function sourcesMessage(isPending: boolean, isError: boolean): string {
  if (isError) {
    return "Sources couldn't be loaded. Try again later.";
  }
  if (isPending) {
    return "Loading sources…";
  }
  return "No sources are set up yet.";
}

/**
 * Search, filters and the primary action for the leads list. The backend filters by several
 * stages at once but by one source and one inquiry type, so those two pills are single-choice.
 */
export function LeadsToolbar(): React.JSX.Element {
  const { params, setFilters, resetFilters, setDeleted, activeFilterCount } = useLeadListParams();
  // LEAD-019 · Deleted leads are listed only for those who may delete them.
  const canDelete = useCan("leads", "delete");
  const deletedView = params.deleted === true;
  // Duplicate review is staff work: a partner user gets an empty queue (walk F-1).
  const canEdit = useCan("leads", "edit");
  const staff = useIsStaff();
  const canReviewDuplicates = canEdit && staff;
  const sources = useQuery(lookupListQueryOptions("lead-sources"));
  const canCreate = useCan("leads", "create");
  // MKT-006 · Staff filter by campaign; a dealer's leads carry none, and dealers can't list them.
  const campaigns = useQuery({ ...activeCampaignsQueryOptions(), enabled: staff });
  const campaignOptions = [
    { value: "none", label: "No campaign" },
    ...(campaigns.data ?? []).map((campaign) => ({ value: campaign.id, label: campaign.name })),
  ];

  // Inactive sources stay listed: old leads still carry them, so they are still worth filtering by.
  const sourceOptions = (sources.data ?? []).map((source) => ({
    value: source.code,
    label: source.name,
  }));

  return (
    <div className="flex flex-col gap-3">
      {deletedView ? (
        <Notice tone="info">
          <p>
            <span className="font-medium">Deleted leads.</span> Nobody without the right to delete
            leads sees them. They can&apos;t be opened or brought back from here yet.
          </p>
        </Notice>
      ) : null}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
          <SearchField
            label="Search leads"
            placeholder="Name, mobile or inquiry number"
            value={params.q}
            onSearch={(q) => {
              setFilters({ q });
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <FilterPill
              label="Stage"
              options={STAGE_OPTIONS}
              selected={params.stage}
              onChange={(stage) => {
                setFilters({ stage });
              }}
            />
            <SingleFilterPill
              label="Source"
              options={sourceOptions}
              selected={params.source}
              emptyMessage={sourcesMessage(sources.isPending, sources.isError)}
              onChange={(source) => {
                setFilters({ source });
              }}
            />
            <LeadAreaFilter
              selected={params.areas}
              onChange={(areas) => {
                setFilters({ areas });
              }}
            />
            <SingleFilterPill
              label="Type"
              options={TYPE_OPTIONS}
              selected={params.type}
              onChange={(type) => {
                setFilters({ type });
              }}
            />
            {staff ? (
              <SingleFilterPill
                label="Campaign"
                options={campaignOptions}
                selected={params.campaign}
                emptyMessage="Campaigns couldn't be loaded."
                onChange={(campaign) => {
                  setFilters({ campaign });
                }}
              />
            ) : null}
            {activeFilterCount > 0 ? (
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                Reset filters
              </Button>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canDelete ? (
            <Button
              variant="ghost"
              onClick={() => {
                setDeleted(!deletedView);
              }}
            >
              {deletedView ? "Back to leads" : "Deleted leads"}
            </Button>
          ) : null}
          {canReviewDuplicates && !deletedView ? (
            <Link href="/leads/duplicates" className={buttonVariants({ variant: "ghost" })}>
              Possible duplicates
            </Link>
          ) : null}
          <DownloadExcelButton
            download={() => exportLeads(params)}
            fallbackName="leads.xlsx"
            what={deletedView ? "deleted leads" : "leads"}
            logger={log}
            dataId="LEAD-009"
          />
          {canCreate && !deletedView ? <NewLeadDialog /> : null}
        </div>
      </div>
    </div>
  );
}

/** Mirrors LeadsToolbar: search field, four filter pills, primary button. */
export function LeadsToolbarSkeleton(): React.JSX.Element {
  return (
    <div
      aria-hidden="true"
      className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"
    >
      <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <Skeleton className="h-control-md w-full rounded-md md:w-72 pointer-coarse:h-control-lg" />
        <div className="flex flex-wrap items-center gap-2">
          <Skeleton className="h-control-sm w-20 rounded-full" />
          <Skeleton className="h-control-sm w-20 rounded-full" />
          <Skeleton className="h-control-sm w-16 rounded-full" />
          <Skeleton className="h-control-sm w-16 rounded-full" />
        </div>
      </div>
      <Skeleton className="h-control-md w-28 rounded-md" />
    </div>
  );
}
