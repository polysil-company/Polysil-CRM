"use client";

import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { activeCampaignsQueryOptions } from "@/features/campaigns/api/campaigns.queries";

/**
 * MKT-006 · Pick the campaign a lead or a QR code came from: the active campaigns, newest first,
 * and "None". A campaign switched off since stays named on what already carries it, and stays
 * offered here while it is the current value, so editing something else doesn't drop it.
 */
export function CampaignSelect({
  id,
  value,
  current,
  onValueChange,
  onBlur,
  ...aria
}: {
  id: string;
  value: string | null;
  /** The campaign the record already names, if any: kept on the list even when switched off. */
  current?: { readonly id: string; readonly name: string } | null;
  onValueChange: (campaignId: string | null) => void;
  onBlur?: () => void;
  "aria-invalid"?: true | undefined;
  "aria-describedby"?: string | undefined;
}): React.JSX.Element {
  const query = useQuery(activeCampaignsQueryOptions());
  const active = (query.data ?? []).map((campaign) => ({
    value: campaign.id,
    label: campaign.name,
  }));
  const items =
    current != null && !active.some((item) => item.value === current.id)
      ? [...active, { value: current.id, label: `${current.name} (switched off)` }]
      : active;
  const listOpen = useRef(false);

  return (
    <div className="flex items-center gap-2">
      <Select
        items={items}
        value={value}
        disabled={query.isPending || query.isError}
        onOpenChange={(open) => {
          listOpen.current = open;
          if (!open) onBlur?.();
        }}
        onValueChange={(next) => {
          onValueChange(typeof next === "string" ? next : null);
        }}
      >
        <SelectTrigger
          id={id}
          onBlur={() => {
            if (!listOpen.current) onBlur?.();
          }}
          {...aria}
        >
          <SelectValue
            placeholder={
              query.isError
                ? "Campaigns couldn't be loaded"
                : query.isPending
                  ? "Loading campaigns…"
                  : items.length === 0
                    ? "No campaigns are running"
                    : "None"
            }
          />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={null} className="text-muted-foreground">
            None
          </SelectItem>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {query.isError ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            void query.refetch();
          }}
        >
          Try again
        </Button>
      ) : null}
    </div>
  );
}
