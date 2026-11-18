"use client";

import { Add01Icon, ArrowRight01Icon, HelpCircleIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { SearchField } from "@/components/patterns/search-field";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { assistantActionsQueryOptions } from "@/features/assistant/api/assistant.queries";
import type { AssistantAction } from "@/features/assistant/api/assistant.schemas";
import { groupByModule, moduleLabel } from "@/features/assistant/lib/assistant-labels";
import { routeFor } from "@/features/assistant/lib/assistant-routes";
import { useModifierKeyLabel } from "@/hooks/use-modifier-key";

/**
 * BOT-002 · Everything the user may do here, by module, each a link to where it starts. The
 * list comes from the backend, so it follows the user's permissions.
 */
export function HelpPage(): React.JSX.Element {
  const modifier = useModifierKeyLabel();
  const [filter, setFilter] = useState("");
  const query = useQuery(assistantActionsQueryOptions());
  const words = filter
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter((word) => word !== "");
  const shown = (query.data ?? []).filter((action) => {
    const text = `${action.title} ${action.hint} ${moduleLabel(action.module)}`.toLowerCase();
    return words.every((word) => text.includes(word));
  });
  const groups = groupByModule(shown);

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-muted-foreground">
        <span className="pointer-coarse:hidden">
          From any page, press{" "}
          <KbdGroup>
            <Kbd>{modifier}</Kbd>
            <Kbd>K</Kbd>
          </KbdGroup>{" "}
          to search
        </span>
        <span className="hidden pointer-coarse:inline">
          From any page, tap the search button at the top to search
        </span>{" "}
        for an action, or for a lead, customer, quotation, order or complaint by its number, mobile
        or name.
      </p>
      <div className="sm:max-w-sm">
        <SearchField
          label="Filter what you can do"
          value={filter}
          placeholder="Filter, e.g. quotation"
          onSearch={setFilter}
        />
      </div>

      {query.status === "pending" ? (
        <HelpPageSkeleton />
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : groups.length === 0 ? (
        <EmptyState
          icon={HelpCircleIcon}
          title={words.length > 0 ? "Nothing matches" : "Nothing to show yet"}
          description={
            words.length > 0
              ? "Try another word, such as order, lead or payment."
              : "Your role has no actions here yet. Ask an administrator if that looks wrong."
          }
          className="rounded-xl border border-dashed border-border py-12"
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {groups.map((group) => (
            <Card key={group.module}>
              <CardHeader>
                <CardTitle level={2}>{moduleLabel(group.module)}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col gap-1">
                  {group.actions.map((action) => (
                    <HelpAction key={action.key} action={action} />
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function HelpAction({ action }: { action: AssistantAction }): React.JSX.Element {
  const starts = action.screen.endsWith(".new");
  return (
    <li>
      <Link
        href={routeFor(action.screen)}
        className="-mx-2 flex items-start gap-3 rounded-md p-2 focus-ring-inset transition-colors duration-fast hover:bg-muted/50 pointer-coarse:min-h-11"
      >
        <Icon
          icon={starts ? Add01Icon : ArrowRight01Icon}
          className="mt-0.5 text-muted-foreground"
        />
        <span className="flex min-w-0 flex-col">
          <span className="text-sm font-medium text-foreground">{action.title}</span>
          <span className="text-xs text-muted-foreground">{action.hint}</span>
        </span>
      </Link>
    </li>
  );
}

function HelpPageSkeleton(): React.JSX.Element {
  return (
    <div
      aria-busy="true"
      aria-label="Loading what you can do"
      className="grid gap-4 md:grid-cols-2"
    >
      <Skeleton className="h-48 w-full rounded-xl" />
      <Skeleton className="h-48 w-full rounded-xl" />
      <Skeleton className="h-48 w-full rounded-xl" />
      <Skeleton className="h-48 w-full rounded-xl" />
    </div>
  );
}
