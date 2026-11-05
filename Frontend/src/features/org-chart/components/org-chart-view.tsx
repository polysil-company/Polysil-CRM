"use client";

import { ArrowDown01Icon, ArrowRight01Icon, UserMultiple02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { parseAsString, parseAsStringLiteral, useQueryStates } from "nuqs";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { orgChartQueryOptions } from "@/features/org-chart/api/org-chart.queries";
import type { OrgChart, OrgNode, OrgPerson } from "@/features/org-chart/api/org-chart.schemas";
import { useCan } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";

/** Levels opened when the chart loads; deeper teams open on demand. */
const OPEN_DEPTH = 2;

function useChartParams(): {
  userId: string | null;
  company: boolean;
} {
  const [values] = useQueryStates({
    user: parseAsString,
    view: parseAsStringLiteral(["company"] as const),
  });
  return {
    userId: values.view === "company" ? null : values.user,
    company: values.view === "company",
  };
}

/**
 * ADMN-008 · The org chart (FS-080): whom I report to, nearest first, and everyone below me as
 * a tree, with counts by role. Open someone below to see their picture (`?user=`); someone who
 * sees every user can switch to the whole company (`?view=company`). Managers come from office
 * and role on the backend, so the chart is always current.
 */
export function OrgChartView(): React.JSX.Element {
  const params = useChartParams();
  const seesEveryone = useCan("users", "view");
  const query = useQuery(orgChartQueryOptions(params));
  const mine = params.userId === null && !params.company;

  return (
    <section aria-label="Org chart" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          href="/org-chart"
          aria-current={mine ? "page" : undefined}
          className={buttonVariants({ variant: mine ? "primary" : "outline", size: "sm" })}
        >
          My team
        </Link>
        {seesEveryone ? (
          <Link
            href="/org-chart?view=company"
            aria-current={params.company ? "page" : undefined}
            className={buttonVariants({
              variant: params.company ? "primary" : "outline",
              size: "sm",
            })}
          >
            Whole company
          </Link>
        ) : null}
      </div>

      {query.isError && isApiError(query.error) && query.error.status === 404 ? (
        <EmptyState
          icon={UserMultiple02Icon}
          title="No reporting line to show"
          description="This person isn't below you, or has left."
          action={
            <Link href="/org-chart" className={buttonVariants({ variant: "outline" })}>
              Back to my team
            </Link>
          }
          className="rounded-xl border border-dashed border-border"
        />
      ) : query.isError && isApiError(query.error) && query.error.status === 403 ? (
        <EmptyState
          icon={UserMultiple02Icon}
          title="The whole company isn't yours to see"
          description="Only someone who sees every user opens it. Your own team is here."
          action={
            <Link href="/org-chart" className={buttonVariants({ variant: "outline" })}>
              My team
            </Link>
          }
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <QueryView query={query} pending={<OrgChartSkeleton />} isEmpty={() => false} empty={null}>
          {(chart) => <Chart chart={chart} company={params.company} mine={mine} />}
        </QueryView>
      )}
    </section>
  );
}

function Chart({
  chart,
  company,
  mine,
}: {
  chart: OrgChart;
  company: boolean;
  mine: boolean;
}): React.JSX.Element {
  const everyone = new Map<string, OrgPerson>();
  for (const person of [
    ...(chart.subject === null ? [] : [chart.subject]),
    ...chart.managers.flat(),
    ...chart.people,
    ...chart.coManagers,
  ]) {
    everyone.set(person.id, person);
  }
  const ids = new Set(chart.people.map((node) => node.id));
  const branches = new Map<string, OrgNode[]>();
  const roots: OrgNode[] = [];
  for (const node of chart.people) {
    const first = node.managerIds[0];
    // Drawn under the first manager when that one is in the tree; otherwise a root.
    if (first !== undefined && ids.has(first)) {
      branches.set(first, [...(branches.get(first) ?? []), node]);
    } else {
      roots.push(node);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {chart.subject === null ? null : (
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-0.5">
              <CardTitle level={2}>{mine ? "You" : chart.subject.name}</CardTitle>
              <CardDescription>
                {chart.subject.roleName} · {chart.subject.office}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {chart.managers.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nobody above: the top of the line.</p>
            ) : (
              <div className="flex flex-col gap-1.5">
                <h3 className="text-xs text-muted-foreground">Reports to, nearest first</h3>
                <ol aria-label="Reports to" className="flex flex-col gap-1.5">
                  {chart.managers.map((step, index) => (
                    // A step has no id of its own; its place in the chain is its identity.
                    <li key={index} className="text-sm text-foreground">
                      {step.map((person, at) => (
                        <span key={person.id}>
                          {at > 0 ? " and " : null}
                          <span className="font-medium">{person.name}</span>
                          <span className="text-muted-foreground">
                            {" "}
                            · {person.roleName}, {person.office}
                          </span>
                        </span>
                      ))}
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {mine ? null : (
              <Link
                href="/org-chart"
                className="w-fit text-sm text-primary-text underline underline-offset-4"
              >
                Back to my team
              </Link>
            )}
          </CardContent>
        </Card>
      )}

      {chart.unplaced.length === 0 ? null : (
        <Notice tone="warning">
          <p className="font-medium">
            {chart.unplaced.length === 1
              ? "1 person can't be placed"
              : `${formatNumber(chart.unplaced.length)} people can't be placed`}
          </p>
          <p>
            {chart.unplaced.map((person) => person.name).join(", ")} sit on the System office. Give
            them a real office in Users &amp; roles.
          </p>
        </Notice>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-1.5">
            <CardTitle level={2}>
              {company ? "The whole company" : mine ? "Your team" : "Their team"}
            </CardTitle>
            {/* An empty team says so once, in the card's body. */}
            {chart.total === 0 ? null : (
              <CardDescription>
                {`${formatNumber(chart.total)} ${chart.total === 1 ? "person" : "people"}${company ? "" : " below"}.`}
              </CardDescription>
            )}
            {chart.byRole.length === 0 ? null : (
              <ul aria-label="By role" className="flex flex-wrap gap-1.5">
                {chart.byRole.map((item) => (
                  <li key={item.roleName}>
                    <Badge variant="neutral">
                      {item.roleName}: {formatNumber(item.count)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {roots.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {mine ? "Nobody reports to you." : "Nobody reports to them."}
            </p>
          ) : (
            <ul aria-label="Team" className="flex flex-col gap-1">
              {roots.map((node) => (
                <TreeNode key={node.id} node={node} depth={1} tree={branches} everyone={everyone} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TreeNode({
  node,
  depth,
  tree,
  everyone,
}: {
  node: OrgNode;
  depth: number;
  tree: ReadonlyMap<string, readonly OrgNode[]>;
  everyone: ReadonlyMap<string, OrgPerson>;
}): React.JSX.Element {
  const below = tree.get(node.id) ?? [];
  const [open, setOpen] = useState(depth < OPEN_DEPTH);
  const others = node.managerIds
    .slice(1)
    .map((id) => everyone.get(id)?.name)
    .filter((name) => name !== undefined);
  const listId = `org-${node.id}`;

  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-start gap-1.5 rounded-lg px-1 py-1.5 hover:bg-accent">
        {below.length === 0 ? (
          <span className="size-8 shrink-0" aria-hidden />
        ) : (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-expanded={open}
            aria-controls={listId}
            aria-label={`${open ? "Hide" : "Show"} ${node.name}'s team`}
            onClick={() => {
              setOpen((current) => !current);
            }}
          >
            <Icon icon={open ? ArrowDown01Icon : ArrowRight01Icon} />
          </Button>
        )}
        <div className="flex min-w-0 flex-col gap-0.5 pt-1">
          <Link
            href={`/org-chart?user=${encodeURIComponent(node.id)}`}
            className="w-fit text-sm font-medium text-foreground underline-offset-4 hover:underline"
          >
            {node.name}
          </Link>
          <span className="text-xs text-muted-foreground">
            {node.roleName} · {node.office}
            {node.teamSize === 0
              ? ""
              : ` · ${formatNumber(node.directReports)} direct, ${formatNumber(node.teamSize)} in all`}
          </span>
          {others.length === 0 ? null : (
            <span className="text-xs text-muted-foreground">
              Also reports to {others.join(", ")}
            </span>
          )}
        </div>
      </div>
      {below.length === 0 || !open ? null : (
        <ul id={listId} className="ml-4 flex flex-col gap-1 border-l border-border pl-3">
          {below.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              tree={tree}
              everyone={everyone}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function OrgChartSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the org chart" className="flex flex-col gap-4">
      <Skeleton className="h-32 w-full rounded-xl" />
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}
