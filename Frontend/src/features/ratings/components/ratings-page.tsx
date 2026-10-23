"use client";

import { StarIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { StarRating } from "@/components/patterns/star-rating";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  ratingListQueryOptions,
  ratingSummaryQueryOptions,
} from "@/features/ratings/api/ratings.queries";
import {
  LOW_RATING_MAX,
  RATING_SUMMARY_GROUPS,
  RATING_TARGETS,
  type RatingSummaryGroup,
} from "@/features/ratings/api/ratings.schemas";
import {
  RATINGS_TABS,
  RATING_SCORE_FILTERS,
  useRatingsParams,
} from "@/features/ratings/hooks/use-ratings-params";
import {
  averageText,
  RATING_TARGET_LABELS,
  SUMMARY_GROUP_LABELS,
} from "@/features/ratings/lib/rating-labels";
import { useIsStaff } from "@/features/session/hooks/use-session";
import { formatNumber } from "@/lib/format";

import { RatingRow } from "./record-ratings";

/**
 * RATE-002, RATE-003 · Every rating the user can see, newest first, with the low ones (1 or 2
 * stars) a click away, and the summary by dealer, product or kind, lowest average first.
 */
export function RatingsPage(): React.JSX.Element {
  const { tab, set } = useRatingsParams();
  return (
    <Tabs
      value={tab}
      onValueChange={(next) => {
        const chosen = RATINGS_TABS.find((value) => value === next);
        if (chosen !== undefined) set({ tab: chosen });
      }}
      className="flex flex-col gap-5"
    >
      <TabsList aria-label="Ratings">
        <TabsTrigger value="list">Ratings</TabsTrigger>
        <TabsTrigger value="summary">Summary</TabsTrigger>
      </TabsList>
      <TabsContent value="list">
        <RatingsList />
      </TabsContent>
      <TabsContent value="summary">
        <RatingsSummary />
      </TabsContent>
    </Tabs>
  );
}

const ALL = "all";

function RatingsList(): React.JSX.Element {
  const staff = useIsStaff();
  const { target, score, set } = useRatingsParams();
  const low = score === "low";
  const query = useInfiniteQuery(
    ratingListQueryOptions({
      target,
      salesOrderId: null,
      complaintId: null,
      partnerId: null,
      maxScore: low ? LOW_RATING_MAX : null,
    }),
  );
  const ratings = query.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = target !== null || low;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <ToggleGroup
          aria-label="Kind"
          value={[target ?? ALL]}
          onValueChange={(next) => {
            const chosen = RATING_TARGETS.find((value) => value === next[0]);
            set({ target: chosen ?? null });
          }}
          className="max-w-full overflow-x-auto"
        >
          <ToggleGroupItem value={ALL}>All kinds</ToggleGroupItem>
          {RATING_TARGETS.map((value) => (
            <ToggleGroupItem key={value} value={value}>
              {RATING_TARGET_LABELS[value]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <ToggleGroup
          aria-label="Stars"
          value={[score]}
          onValueChange={(next) => {
            const chosen = RATING_SCORE_FILTERS.find((value) => value === next[0]);
            if (chosen !== undefined) set({ score: chosen });
          }}
        >
          <ToggleGroupItem value="all">Any stars</ToggleGroupItem>
          <ToggleGroupItem value="low">1 or 2 stars</ToggleGroupItem>
        </ToggleGroup>
      </div>

      {query.status === "pending" ? (
        <RatingsListSkeleton />
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : ratings.length === 0 ? (
        <EmptyState
          icon={StarIcon}
          title={low ? "No unhappy customers" : filtered ? "No ratings match" : "No ratings yet"}
          description={
            low
              ? "No rating of 1 or 2 stars in what you can see."
              : "Ratings are recorded on a shipped order and on a closed complaint."
          }
          className="rounded-xl border border-dashed border-border py-12"
        />
      ) : (
        <Card>
          <CardContent className="pt-4">
            <ul aria-label="Ratings, newest first" className="flex flex-col divide-y divide-border">
              {ratings.map((rating) => (
                <RatingRow key={rating.id} rating={rating} staff={staff} showDocument />
              ))}
            </ul>
            {query.hasNextPage ? (
              <div className="mt-4 flex justify-center">
                <Button
                  variant="outline"
                  size="sm"
                  state={query.isFetchingNextPage ? "loading" : "idle"}
                  loadingLabel="Loading…"
                  onClick={() => {
                    void query.fetchNextPage();
                  }}
                >
                  Show more
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function RatingsListSkeleton(): React.JSX.Element {
  return (
    <div aria-busy="true" aria-label="Loading ratings" className="flex flex-col gap-2">
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-16 w-full rounded-xl" />
    </div>
  );
}

const SUMMARY_KEY_HEADINGS: Readonly<Record<RatingSummaryGroup, string>> = {
  partner: "Dealer",
  product: "Product",
  target: "Kind",
};

function RatingsSummary(): React.JSX.Element {
  const { group, set } = useRatingsParams();
  const query = useQuery(ratingSummaryQueryOptions(group));
  const nameOf = (id: string, name: string): string => {
    if (group !== "target") return name;
    const target = RATING_TARGETS.find((value) => value === id);
    return target === undefined ? name : RATING_TARGET_LABELS[target];
  };

  return (
    <div className="flex flex-col gap-4">
      <ToggleGroup
        aria-label="Group by"
        value={[group]}
        onValueChange={(next) => {
          const chosen = RATING_SUMMARY_GROUPS.find((value) => value === next[0]);
          if (chosen !== undefined) set({ group: chosen });
        }}
      >
        {RATING_SUMMARY_GROUPS.map((value) => (
          <ToggleGroupItem key={value} value={value}>
            {SUMMARY_GROUP_LABELS[value]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      {query.status === "pending" ? (
        <RatingsListSkeleton />
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : query.data.length === 0 ? (
        <EmptyState
          icon={StarIcon}
          title="Nothing to sum up yet"
          description="The summary fills in as ratings are recorded."
          className="rounded-xl border border-dashed border-border py-12"
        />
      ) : (
        <Card>
          <CardContent className="overflow-x-auto pt-4">
            <table className="w-full text-sm">
              <caption className="sr-only">
                Ratings {SUMMARY_GROUP_LABELS[group].toLowerCase()}, lowest average first
              </caption>
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-3 font-medium">
                    {SUMMARY_KEY_HEADINGS[group]}
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Average
                  </th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">
                    Ratings
                  </th>
                  <th scope="col" className="py-2 text-right font-medium">
                    1 or 2 stars
                  </th>
                </tr>
              </thead>
              <tbody>
                {query.data.map((row) => (
                  <tr key={row.key.id} className="border-b border-border last:border-0">
                    <th scope="row" className="py-2.5 pr-3 text-left font-medium text-foreground">
                      {nameOf(row.key.id, row.key.name)}
                    </th>
                    <td className="py-2.5 pr-3">
                      <span className="inline-flex items-center gap-2 whitespace-nowrap">
                        <StarRating score={row.average} size="xs" />
                        <span className="text-foreground tabular-nums">
                          {averageText(row.average)}
                        </span>
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-right text-foreground tabular-nums">
                      {formatNumber(row.count)}
                    </td>
                    <td
                      className={
                        row.low > 0
                          ? "py-2.5 text-right font-medium text-danger tabular-nums"
                          : "py-2.5 text-right text-muted-foreground tabular-nums"
                      }
                    >
                      {formatNumber(row.low)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
