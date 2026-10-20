"use client";

import { Add01Icon, Cancel01Icon, MapsLocation01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { territoryListQueryOptions } from "@/features/masters/api/masters.queries";
import {
  TERRITORY_LEVELS,
  type Territory,
  type TerritoryLevel,
} from "@/features/masters/api/masters.schemas";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

import { TerritoryForm } from "./territory-dialog";

export const TERRITORY_LEVEL_LABELS: Readonly<Record<TerritoryLevel, string>> = {
  state: "State",
  district: "District",
  taluka: "Taluka",
  village: "Village",
};

const PLURAL: Readonly<Record<TerritoryLevel, string>> = {
  state: "States",
  district: "Districts",
  taluka: "Talukas",
  village: "Villages",
};

type LevelFilter = TerritoryLevel | "all";

/** The level one down, or null for a village. */
export function childLevel(level: TerritoryLevel): TerritoryLevel | null {
  return TERRITORY_LEVELS[TERRITORY_LEVELS.indexOf(level) + 1] ?? null;
}

/**
 * MSTR-012 · The territory tree: states, their districts, talukas and villages, each with its
 * code and where it sits. Those who may edit masters add one under the level above, rename it
 * and set its code; a state's code locks once a lead is numbered with it.
 */
export function TerritoriesPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim(), 250);
  const [level, setLevel] = useState<LevelFilter>("state");
  const [parent, setParent] = useState<Territory | null>(null);
  const [editing, setEditing] = useState<Territory | "new" | null>(null);
  const query = useInfiniteQuery(
    territoryListQueryOptions({
      level: level === "all" ? null : level,
      parentId: parent?.id ?? null,
      q,
    }),
  );
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const what = level === "all" ? "territories" : PLURAL[level].toLowerCase();

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div className="flex flex-col gap-0.5">
          <CardTitle>Territories</CardTitle>
          <CardDescription>
            States, their districts, talukas and villages. A state&apos;s code numbers its leads,
            like POL/GJ/2026-27/00001.
          </CardDescription>
        </div>
        {canEdit ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEditing("new");
            }}
          >
            <Icon icon={Add01Icon} />
            New territory
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <SearchField
            label="Search territories"
            value={search}
            placeholder="Name or code"
            onSearch={setSearch}
          />
          <ToggleGroup
            aria-label="Level"
            value={[level]}
            className="flex-wrap"
            onValueChange={(next) => {
              const chosen = (["all", ...TERRITORY_LEVELS] as const).find(
                (item) => item === next[0],
              );
              if (chosen !== undefined) setLevel(chosen);
            }}
          >
            <ToggleGroupItem value="all">All</ToggleGroupItem>
            {TERRITORY_LEVELS.map((item) => (
              <ToggleGroupItem key={item} value={item}>
                {PLURAL[item]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        {parent === null ? null : (
          <div className="flex items-center gap-2">
            <Badge variant="primary" className="gap-1 pr-1">
              In {parent.name}
              <button
                type="button"
                aria-label={`Show territories outside ${parent.name} too`}
                className="rounded-full p-0.5 hover:bg-accent"
                onClick={() => {
                  setParent(null);
                }}
              >
                <Icon icon={Cancel01Icon} size="sm" />
              </button>
            </Badge>
          </div>
        )}
        {query.status === "pending" ? (
          <TerritoriesSkeleton />
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={MapsLocation01Icon}
            title={q === "" ? `No ${what} here` : `No territory matches “${q}”`}
            description={
              parent === null ? "Try another level or name." : `Nothing in ${parent.name} yet.`
            }
            className="py-8"
          />
        ) : (
          <>
            <ul aria-label="Territories" className="flex flex-col divide-y divide-border">
              {rows.map((territory) => (
                <TerritoryRow
                  key={territory.id}
                  territory={territory}
                  canEdit={canEdit}
                  onOpen={(child) => {
                    setParent(territory);
                    setLevel(child);
                  }}
                  onEdit={() => {
                    setEditing(territory);
                  }}
                />
              ))}
            </ul>
            {query.hasNextPage ? (
              <Button
                variant="outline"
                size="sm"
                className="self-center"
                disabled={query.isFetchingNextPage}
                onClick={() => {
                  void query.fetchNextPage();
                }}
              >
                {query.isFetchingNextPage ? "Loading…" : "Show more"}
              </Button>
            ) : null}
          </>
        )}
      </CardContent>
      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      >
        <DialogContent size="sm">
          {editing === null ? null : (
            <TerritoryForm
              territory={editing === "new" ? null : editing}
              onDone={() => {
                setEditing(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function TerritoryRow({
  territory,
  canEdit,
  onOpen,
  onEdit,
}: {
  territory: Territory;
  canEdit: boolean;
  onOpen: (child: TerritoryLevel) => void;
  onEdit: () => void;
}): React.JSX.Element {
  const child = childLevel(territory.level);
  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground">{territory.name}</span>
          {territory.code === null ? null : (
            <span className="font-mono text-xs text-muted-foreground">{territory.code}</span>
          )}
          <Badge size="sm" variant="neutral">
            {TERRITORY_LEVEL_LABELS[territory.level]}
          </Badge>
        </span>
        <span className="text-xs text-muted-foreground">
          {territory.parent === null ? "Top level" : `In ${territory.parent.name}`}
          {territory.codeLocked ? " · the code numbers its leads and can't change" : ""}
          {territory.level === "state" && territory.code === null
            ? " · no code yet: leads here can't be numbered"
            : ""}
        </span>
      </div>
      <div className="flex shrink-0 gap-2">
        {child === null ? null : (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`${PLURAL[child]} in ${territory.name}`}
            onClick={() => {
              onOpen(child);
            }}
          >
            {PLURAL[child]}
          </Button>
        )}
        {canEdit ? (
          <Button
            variant="outline"
            size="sm"
            aria-label={`Edit ${territory.name}`}
            onClick={onEdit}
          >
            Edit
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function TerritoriesSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading territories" className="flex flex-col gap-3">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex flex-col gap-1.5 py-1">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-40" />
        </div>
      ))}
    </div>
  );
}
