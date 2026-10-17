"use client";

import { Add01Icon, Megaphone02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { campaignListQueryOptions } from "@/features/campaigns/api/campaigns.queries";
import { CAMPAIGN_TYPES, type Campaign } from "@/features/campaigns/api/campaigns.schemas";
import { CAMPAIGN_TYPE_LABELS, campaignDates } from "@/features/campaigns/lib/campaign-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { formatCount, formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CampaignDialog } from "./campaign-dialog";
import { CampaignForm } from "./campaign-form";

const STATES = ["active", "off", "all"] as const;
const STATE_OPTIONS = [
  { value: "active", label: "Running" },
  { value: "off", label: "Switched off" },
  { value: "all", label: "All" },
] as const;
const TYPE_OPTIONS = CAMPAIGN_TYPES.map((type) => ({
  value: type,
  label: CAMPAIGN_TYPE_LABELS[type],
}));

/**
 * MKT-005 · Campaigns: the fairs, meetings and drives that bring leads in, newest start first,
 * with how many leads each brought and, for those who may see it, what it cost. Marketing adds
 * one and opens one to change it, switch it off or delete it. Filters and the open campaign are
 * in the URL.
 */
export function CampaignsPage(): React.JSX.Element {
  const canCreate = useCan("campaigns", "create");
  const [q, setQ] = useQueryState("q", parseAsString.withDefault(""));
  const [type, setType] = useQueryState("type", parseAsStringLiteral(CAMPAIGN_TYPES));
  const [state, setState] = useQueryState(
    "state",
    parseAsStringLiteral(STATES).withDefault("active"),
  );
  const [openId, setOpenId] = useQueryState("campaign", parseAsString);
  const [adding, setAdding] = useState(false);
  const query = useQuery(
    campaignListQueryOptions({
      active: state === "all" ? null : state === "active",
      type,
      q: q.trim(),
    }),
  );
  const filtered = q.trim() !== "" || type !== null || state !== "active";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
          <SearchField
            label="Search campaigns"
            placeholder="Campaign name"
            value={q}
            onSearch={(next) => {
              void setQ(next === "" ? null : next);
            }}
          />
          <div className="flex flex-wrap items-center gap-2">
            <SingleFilterPill
              label="Type"
              options={TYPE_OPTIONS}
              selected={type}
              onChange={(next) => {
                void setType(CAMPAIGN_TYPES.find((value) => value === next) ?? null);
              }}
            />
            <SingleFilterPill
              label="Showing"
              options={STATE_OPTIONS}
              selected={state}
              onChange={(next) => {
                const chosen = STATES.find((value) => value === next);
                void setState(chosen === undefined || chosen === "active" ? null : chosen);
              }}
            />
            {filtered ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  void setQ(null);
                  void setType(null);
                  void setState(null);
                }}
              >
                Reset filters
              </Button>
            ) : null}
          </div>
        </div>
        {canCreate ? (
          <Button
            onClick={() => {
              setAdding(true);
            }}
          >
            <Icon icon={Add01Icon} />
            New campaign
          </Button>
        ) : null}
      </div>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading campaigns" className="grid gap-3 md:grid-cols-2">
          {[0, 1, 2, 3].map((card) => (
            <Skeleton key={card} className="h-32 w-full rounded-xl" />
          ))}
        </div>
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : query.data.length === 0 ? (
        <EmptyState
          icon={Megaphone02Icon}
          title={filtered ? "No campaigns match" : "No campaigns yet"}
          description={
            filtered
              ? "Try another name or type, or show the switched-off ones too."
              : "Add the fairs, meetings and drives you run, so leads can be counted under them."
          }
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {formatCount(query.data.length)} {query.data.length === 1 ? "campaign" : "campaigns"},
            newest first.
          </p>
          <ul aria-label="Campaigns" className="grid gap-3 md:grid-cols-2">
            {query.data.map((campaign) => (
              <CampaignCard
                key={campaign.id}
                campaign={campaign}
                onOpen={() => {
                  void setOpenId(campaign.id);
                }}
              />
            ))}
          </ul>
        </div>
      )}

      <Dialog
        open={openId !== null}
        onOpenChange={(open) => {
          if (!open) void setOpenId(null);
        }}
      >
        <DialogContent size="lg">
          {openId === null ? null : (
            <CampaignDialog
              key={openId}
              campaignId={openId}
              onClose={() => {
                void setOpenId(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          {adding ? (
            <CampaignForm
              campaign={null}
              onClose={() => {
                setAdding(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CampaignCard({
  campaign,
  onOpen,
}: {
  campaign: Campaign;
  onOpen: () => void;
}): React.JSX.Element {
  const cost = campaign.costActual ?? campaign.costPlanned;
  return (
    <li>
      <button
        type="button"
        aria-label={`Open ${campaign.name}`}
        className={cn(
          "flex size-full press-scale flex-col gap-3 rounded-xl border border-border bg-card p-4 text-left transition-colors duration-fast ease-out hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          !campaign.active && "bg-muted",
        )}
        onClick={onOpen}
      >
        <span className="flex flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-foreground">{campaign.name}</span>
            {campaign.active ? null : (
              <Badge variant="neutral" size="sm">
                Switched off
              </Badge>
            )}
          </span>
          <span className="text-xs text-muted-foreground">
            {CAMPAIGN_TYPE_LABELS[campaign.type]}
            {campaign.territory === null ? "" : ` · ${campaign.territory.name}`} ·{" "}
            {campaignDates(campaign.startDate, campaign.endDate)}
          </span>
        </span>
        <span className="flex flex-wrap items-end justify-between gap-2">
          <span className="text-sm text-foreground tabular-nums">
            <span className="text-lg font-semibold">{formatCount(campaign.leadCount)}</span>{" "}
            {campaign.leadCount === 1 ? "lead" : "leads"}
          </span>
          {cost === null ? null : (
            <span className="text-xs text-muted-foreground tabular-nums">
              {campaign.costActual === null ? "Planned " : "Spent "}
              {formatInr(cost)}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}
