"use client";

import { Add01Icon, Building03Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

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
import { useSetOfficeOpen } from "@/features/masters/api/masters.mutations";
import { officeListQueryOptions } from "@/features/masters/api/masters.queries";
import {
  OFFICE_STATES,
  type Office,
  type OfficeState,
} from "@/features/masters/api/masters.schemas";
import { roleListQueryOptions } from "@/features/users/api/users.queries";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { OfficeForm } from "./office-dialog";

const log = createLogger({
  file: "features/masters/components/offices-panel.tsx",
  dataId: "MSTR-011",
});

const STATE_LABELS: Readonly<Record<OfficeState, string>> = {
  open: "Open",
  closed: "Closed",
  all: "All",
};

/** "3 people", "No one". */
export function peopleLabel(count: number): string {
  if (count === 0) return "No one";
  return `${formatNumber(count)} ${count === 1 ? "person" : "people"}`;
}

/** Why an office can't be closed, in words: the backend answers `422 fields.id`. */
export function closeRefusal(error: unknown, office: Office): string | null {
  if (!isApiError(error) || error.status !== 422) return null;
  const fields = readFieldErrors(error) ?? {};
  if (fields.id === undefined) return null;
  return `${peopleLabel(office.activeUsers)} still work from ${office.name}. Move them to another office, or deactivate them in Users & roles, then close it.`;
}

/**
 * MSTR-011 · The office tree: each office's place, the territory it covers, its level and how
 * many people work from it. Those who may edit masters add offices, rename and move them,
 * and close or reopen them. An office with active people can't be closed.
 */
export function OfficesPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim(), 250);
  const [state, setState] = useState<OfficeState>("open");
  const query = useInfiniteQuery(officeListQueryOptions({ q, state }));
  const roles = useQuery(roleListQueryOptions());
  const [editing, setEditing] = useState<Office | "new" | null>(null);
  const offices = query.data?.pages.flatMap((page) => page.items) ?? [];
  const levelName = (level: number): string =>
    roles.data?.find((role) => !role.portal && role.level === level)?.name ??
    `Level ${String(level)}`;

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div className="flex flex-col gap-0.5">
          <CardTitle>Offices</CardTitle>
          <CardDescription>
            Where people work from, and the territory each office covers.
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
            New office
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <SearchField
            label="Search offices"
            value={search}
            placeholder="Office name"
            onSearch={setSearch}
          />
          <ToggleGroup
            aria-label="Show"
            value={[state]}
            onValueChange={(next) => {
              const chosen = OFFICE_STATES.find((item) => item === next[0]);
              if (chosen !== undefined) setState(chosen);
            }}
          >
            {OFFICE_STATES.map((item) => (
              <ToggleGroupItem key={item} value={item}>
                {STATE_LABELS[item]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        {query.status === "pending" ? (
          <OfficesSkeleton />
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        ) : offices.length === 0 ? (
          <EmptyState
            icon={Building03Icon}
            title={
              q === ""
                ? `No ${STATE_LABELS[state].toLowerCase()} offices`
                : `No office matches “${q}”`
            }
            description={
              state === "open" ? "Try All to include closed offices." : "Try another name."
            }
            className="py-8"
          />
        ) : (
          <>
            <ul aria-label="Offices" className="flex flex-col divide-y divide-border">
              {offices.map((office) => (
                <OfficeRow
                  key={office.id}
                  office={office}
                  levelName={levelName(office.roleLevel)}
                  canEdit={canEdit}
                  onEdit={() => {
                    setEditing(office);
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
            <OfficeForm
              office={editing === "new" ? null : editing}
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

function OfficeRow({
  office,
  levelName,
  canEdit,
  onEdit,
}: {
  office: Office;
  levelName: string;
  canEdit: boolean;
  onEdit: () => void;
}): React.JSX.Element {
  const setOpen = useSetOfficeOpen();
  const [refusal, setRefusal] = useState<string | null>(null);
  const toggle = useAsyncAction({
    action: () => setOpen.mutateAsync({ officeId: office.id, open: !office.isOpen }),
    logger: log,
    fn: office.isOpen ? "handleCloseOffice" : "handleReopenOffice",
    dataId: "MSTR-011",
    onSuccess: (saved) => {
      setRefusal(null);
      toast.success(saved.isOpen ? `${saved.name} reopened` : `${saved.name} closed`);
    },
    onError: (error) => {
      const reason = closeRefusal(error, office);
      if (reason !== null) {
        setRefusal(reason);
        return;
      }
      toast.error(`${office.name} not changed`, {
        description: toUserFacingError(error).description,
      });
    },
  });
  const where = [
    office.parent === null ? "Top level" : `Under ${office.parent.name}`,
    office.territory === null ? "HQ unit" : office.territory.name,
    levelName,
  ].join(" · ");

  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground">{office.name}</span>
          {office.isOpen ? null : (
            <Badge size="sm" variant="neutral">
              Closed
            </Badge>
          )}
        </span>
        <span className="text-xs text-muted-foreground">{where}</span>
        <span className="text-xs text-muted-foreground">{peopleLabel(office.activeUsers)}</span>
        {refusal === null ? null : (
          <p role="alert" className="text-xs text-danger">
            {refusal}
          </p>
        )}
      </div>
      {canEdit ? (
        <div className="flex shrink-0 gap-2">
          {office.isOpen ? (
            <Button variant="outline" size="sm" aria-label={`Edit ${office.name}`} onClick={onEdit}>
              Edit
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            aria-label={office.isOpen ? `Close ${office.name}` : `Reopen ${office.name}`}
            state={toggle.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
            onClick={() => {
              void toggle.run();
            }}
          >
            {office.isOpen ? "Close" : "Reopen"}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

function OfficesSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading offices" className="flex flex-col gap-3">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex flex-col gap-1.5 py-1">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-72" />
        </div>
      ))}
    </div>
  );
}
