"use client";

import { Add01Icon, DiscountTag01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { schemeListQueryOptions } from "@/features/schemes/api/schemes.queries";
import {
  SCHEME_STATUSES,
  SCHEME_TYPES,
  type Scheme,
  type SchemeListParams,
} from "@/features/schemes/api/schemes.schemas";
import {
  benefitText,
  conditionText,
  SCHEME_STATE_LABELS,
  SCHEME_TYPE_LABELS,
  schemeState,
  validityText,
  type SchemeState,
} from "@/features/schemes/lib/scheme-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";

const STATUS_OPTIONS = [
  {
    value: "current",
    label: "Running now",
    description: "Switched on, and today within its dates.",
  },
  { value: "active", label: "Switched on", description: "Including those not started or ended." },
  {
    value: "inactive",
    label: "Switched off",
    description: "No new benefits; credits stay usable.",
  },
] as const satisfies readonly {
  value: (typeof SCHEME_STATUSES)[number];
  label: string;
  description: string;
}[];

const TYPE_OPTIONS = SCHEME_TYPES.map((type) => ({ value: type, label: SCHEME_TYPE_LABELS[type] }));

export const STATE_BADGE: Readonly<Record<SchemeState, BadgeVariant>> = {
  running: "success",
  scheduled: "info",
  ended: "neutral",
  off: "outline",
};

/**
 * SCHM-001 · The schemes, newest first. Staff see every scheme, filtered by status, type and a
 * search; those who may create one get New scheme. A partner user sees the running schemes
 * aimed at it.
 */
export function SchemesList(): React.JSX.Element {
  const staff = useIsStaff();
  const canCreate = useCan("schemes", "create");
  const [values, setValues] = useQueryStates({
    status: parseAsStringLiteral(SCHEME_STATUSES),
    type: parseAsStringLiteral(SCHEME_TYPES),
    q: parseAsString.withDefault(""),
  });
  const params: SchemeListParams = {
    status: staff ? values.status : "current",
    type: values.type,
    q: values.q.trim(),
  };
  const query = useInfiniteQuery(schemeListQueryOptions(params));
  const filtered = (staff && values.status !== null) || values.type !== null || params.q !== "";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2.5 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Search schemes"
          placeholder="Code or name"
          value={values.q}
          onSearch={(q) => {
            void setValues({ q: q === "" ? null : q });
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          {staff ? (
            <SingleFilterPill
              label="Status"
              options={STATUS_OPTIONS}
              selected={values.status}
              onChange={(status) => {
                void setValues({ status });
              }}
            />
          ) : null}
          <SingleFilterPill
            label="Type"
            options={TYPE_OPTIONS}
            selected={values.type}
            onChange={(type) => {
              void setValues({ type });
            }}
          />
          {filtered ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void setValues({ status: null, type: null, q: null });
              }}
            >
              Reset filters
            </Button>
          ) : null}
        </div>
        {canCreate ? (
          <Link href="/schemes/new" className={buttonVariants({ className: "md:ml-auto" })}>
            <Icon icon={Add01Icon} />
            New scheme
          </Link>
        ) : null}
      </div>

      <QueryView
        query={query}
        pending={<SchemesSkeleton />}
        isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
        empty={
          <EmptyState
            icon={DiscountTag01Icon}
            title={
              filtered
                ? "No schemes match"
                : staff
                  ? "No schemes yet"
                  : "No schemes for you right now"
            }
            description={
              filtered
                ? "Try fewer filters, or another search."
                : staff
                  ? "Schemes give dealers a discount, points or a credit on the orders that qualify."
                  : "When Polysil runs a scheme for you, it shows here."
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ul className="flex flex-col gap-3">
              {data.pages
                .flatMap((page) => page.items)
                .map((scheme) => (
                  <li key={scheme.id}>
                    <SchemeRow scheme={scheme} />
                  </li>
                ))}
            </ul>
            {query.hasNextPage ? (
              <Button
                variant="outline"
                className="self-center"
                disabled={query.isFetchingNextPage}
                onClick={() => {
                  void query.fetchNextPage();
                }}
              >
                {query.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            ) : null}
          </div>
        )}
      </QueryView>
    </div>
  );
}

function SchemeRow({ scheme }: { scheme: Scheme }): React.JSX.Element {
  const state = schemeState(scheme);
  return (
    <Card className="relative flex flex-col gap-2 p-4 transition-colors duration-fast ease-out hover:bg-muted/40">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="text-base font-semibold text-foreground">
            <Link
              href={`/schemes/${scheme.id}`}
              className="after:absolute after:inset-0 after:rounded-xl focus-visible:outline-none"
            >
              {scheme.name}
            </Link>
          </h2>
          <span className="font-mono text-xs text-muted-foreground">{scheme.code}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="neutral">{SCHEME_TYPE_LABELS[scheme.type]}</Badge>
          <Badge variant={STATE_BADGE[state]}>{SCHEME_STATE_LABELS[state]}</Badge>
        </div>
      </div>
      <p className="text-sm text-foreground">
        {benefitText(scheme)} · {conditionText(scheme)}
      </p>
      <p className="text-xs text-muted-foreground">{validityText(scheme)}</p>
    </Card>
  );
}

function SchemesSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading schemes" className="flex flex-col gap-3">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-28 w-full rounded-xl" />
      ))}
    </div>
  );
}
