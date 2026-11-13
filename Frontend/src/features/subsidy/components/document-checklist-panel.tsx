"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { documentTypesQueryOptions } from "@/features/subsidy/api/subsidy-applications.queries";
import type { DocumentType } from "@/features/subsidy/api/subsidy-applications.schemas";

/**
 * SUBS-007 · The document checklist every application is given (`GET /subsidy-document-types`):
 * the enclosures GGRC asks for. Read only; the backend keeps the list, and none is required yet.
 * Items no longer asked for stay listed, marked, because older applications still hold files
 * against them.
 */
export function DocumentChecklistPanel(): React.JSX.Element {
  const query = useQuery(documentTypesQueryOptions());

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>Document checklist</CardTitle>
          <CardDescription>
            The enclosures each application collects, the same for every scheme. None is required
            yet; files are added on the application.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <QueryView
          query={query}
          pending={<ChecklistSkeleton />}
          isEmpty={(items) => items.length === 0}
          empty={<p className="text-sm text-muted-foreground">The checklist is empty.</p>}
        >
          {(items) => <ChecklistItems items={items} />}
        </QueryView>
      </CardContent>
    </Card>
  );
}

function ChecklistItems({ items }: { items: readonly DocumentType[] }): React.JSX.Element {
  const active = items.filter((item) => item.active).length;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        {active === items.length
          ? `${String(items.length)} items`
          : `${String(active)} of ${String(items.length)} items still asked for`}
      </p>
      <ol aria-label="Document checklist" className="flex flex-col divide-y divide-border">
        {items.map((item, index) => (
          <li key={item.id} className="flex items-start gap-3 py-2.5">
            <span className="w-6 shrink-0 text-right text-sm text-muted-foreground tabular-nums">
              {index + 1}.
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-sm text-foreground">{item.name}</span>
              <span className="font-mono text-xs text-muted-foreground">{item.code}</span>
            </span>
            {item.active ? null : (
              <Badge size="sm" variant="neutral">
                No longer asked for
              </Badge>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function ChecklistSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the checklist" className="flex flex-col gap-3">
      {[0, 1, 2, 3, 4].map((row) => (
        <div key={row} className="flex flex-col gap-1.5 py-1">
          <Skeleton className="h-4 w-56" />
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  );
}
