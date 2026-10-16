"use client";

import { Add01Icon, UserGroupIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type * as React from "react";

import { DownloadExcelButton } from "@/components/patterns/download-excel-button";
import { EmptyState } from "@/components/patterns/empty-state";
import { SingleFilterPill } from "@/components/patterns/filter-pill";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { SearchField } from "@/components/patterns/search-field";
import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/features/session/hooks/use-session";
import { exportUsers } from "@/features/users/api/users.api";
import { roleListQueryOptions, userListQueryOptions } from "@/features/users/api/users.queries";
import { USER_TYPES, type UserListParams, type UserRow } from "@/features/users/api/users.schemas";
import { USER_STATUSES, useUserListParams } from "@/features/users/hooks/use-user-list-params";
import { anchorOf, signInIdOf, USER_TYPE_LABELS } from "@/features/users/lib/user-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatCount } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "features/users/components/users-list.tsx", dataId: "ADMN-001" });

const SKELETON_ROWS = 6;

const TYPE_OPTIONS = USER_TYPES.map((value) => ({ value, label: USER_TYPE_LABELS[value] }));
const STATUS_OPTIONS = USER_STATUSES.map((value) => ({
  value,
  label: value === "active" ? "Active" : "Deactivated",
}));

/**
 * ADMN-001 · People: staff and partner users in the caller's scope, newest first, searched by
 * name, email or mobile and filtered by type, role and active — all in the URL. Whoever may
 * add people gets "New person"; the list downloads as Excel with the filters on screen.
 */
export function UsersList(): React.JSX.Element {
  const { params, status, activeFilterCount, setFilters, resetFilters } = useUserListParams();
  const canCreate = useCan("users", "create");
  const roles = useQuery(roleListQueryOptions());
  const roleOptions = (roles.data ?? []).map((role) => ({ value: role.code, label: role.name }));

  return (
    <section aria-label="People" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <SearchField
          label="Search people"
          placeholder="Name, email or mobile"
          value={params.q}
          onSearch={(q) => {
            setFilters({ q });
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <DownloadExcelButton
            download={() => exportUsers({ ...params, cursor: null })}
            fallbackName="users.xlsx"
            what="people"
            logger={log}
            dataId="ADMN-001"
          />
          {canCreate ? (
            <Link href="/users/new" className={buttonVariants()}>
              <Icon icon={Add01Icon} />
              New person
            </Link>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SingleFilterPill
          label="Type"
          options={TYPE_OPTIONS}
          selected={params.userType}
          onChange={(userType) => {
            setFilters({ userType });
          }}
        />
        <SingleFilterPill
          label="Role"
          options={roleOptions}
          selected={params.role}
          emptyMessage={roles.isPending ? "Loading roles…" : "No roles to choose from."}
          onChange={(role) => {
            setFilters({ role });
          }}
        />
        <SingleFilterPill
          label="Status"
          options={STATUS_OPTIONS}
          selected={status}
          onChange={(next) => {
            setFilters({ status: next });
          }}
        />
        {activeFilterCount > 0 ? (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Reset filters
          </Button>
        ) : null}
      </div>

      <UserRows params={params} filtered={activeFilterCount > 0} onReset={resetFilters} />
    </section>
  );
}

function UserRows({
  params,
  filtered,
  onReset,
}: {
  params: Omit<UserListParams, "cursor">;
  filtered: boolean;
  onReset: () => void;
}): React.JSX.Element {
  const query = useInfiniteQuery(userListQueryOptions(params));
  const total = query.data?.pages[0]?.total ?? null;
  const capped = query.data?.pages[0]?.totalCapped ?? false;

  return (
    <QueryView
      query={query}
      pending={<UsersListSkeleton />}
      isEmpty={(data) => data.pages.every((page) => page.items.length === 0)}
      empty={
        <EmptyState
          icon={UserGroupIcon}
          title={filtered ? "Nobody matches these filters" : "Nobody in your scope yet"}
          description={
            filtered
              ? "Change or reset the filters to see more."
              : "People you add, staff or partner users, appear here."
          }
          action={
            filtered ? (
              <Button variant="outline" size="sm" onClick={onReset}>
                Reset filters
              </Button>
            ) : undefined
          }
          className="rounded-xl border border-dashed border-border"
        />
      }
    >
      {(data) => (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {total === null
              ? "Newest first."
              : `${formatCount(total, { atLeast: capped })} ${total === 1 ? "person" : "people"}, newest first.`}
          </p>
          <ul aria-label="People" className="flex flex-col gap-2">
            {data.pages.flatMap((page) =>
              page.items.map((user) => <UserListRow key={user.id} user={user} />),
            )}
          </ul>
          {query.hasNextPage ? (
            <div className="flex flex-col items-start gap-2">
              {query.isFetchNextPageError ? (
                <p role="alert" className="text-xs text-danger">
                  {toUserFacingError(query.error).title}. The people above are still current.
                </p>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                state={query.isFetchingNextPage ? "loading" : "idle"}
                loadingLabel="Loading…"
                onClick={() => {
                  void query.fetchNextPage();
                }}
              >
                {query.isFetchNextPageError ? "Try again" : "Show more"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </QueryView>
  );
}

function UserListRow({ user }: { user: UserRow }): React.JSX.Element {
  const role = user.role?.name ?? USER_TYPE_LABELS[user.userType];
  return (
    <li>
      <Link
        href={`/users/${user.id}`}
        aria-label={`${user.name}, ${role}, ${anchorOf(user)}${user.active ? "" : ", deactivated"}`}
        className="flex items-start gap-3 rounded-xl border border-border bg-card p-3 transition-colors duration-fast hover:bg-accent sm:items-center sm:p-4"
      >
        <Avatar size="sm">
          <AvatarFallback>{getInitials(user.name)}</AvatarFallback>
        </Avatar>
        <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center sm:gap-4">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-sm font-medium text-foreground">{user.name}</span>
              {user.active ? null : <Badge variant="neutral">Deactivated</Badge>}
              {user.mustChangePassword && user.active ? (
                <Badge variant="warning">Temporary password</Badge>
              ) : null}
            </div>
            <span className="truncate text-xs text-muted-foreground">{signInIdOf(user)}</span>
          </div>
          <div className="flex min-w-0 flex-col gap-0.5 sm:w-56">
            <span className="truncate text-sm text-foreground">{role}</span>
            <span className="truncate text-xs text-muted-foreground">{anchorOf(user)}</span>
          </div>
          <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground sm:w-44 sm:flex-col sm:items-end sm:text-right">
            <span>
              {user.lastLoginAt === null ? (
                "Never signed in"
              ) : (
                <>
                  Signed in <RelativeDate value={user.lastLoginAt} />
                </>
              )}
            </span>
            {user.openLeads === null ? null : (
              <span>
                {user.openLeads === 0
                  ? "No open leads"
                  : `${String(user.openLeads)} open lead${user.openLeads === 1 ? "" : "s"}`}
              </span>
            )}
          </div>
        </div>
      </Link>
    </li>
  );
}

export function UsersListSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading people" className="flex flex-col gap-2">
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 rounded-xl border border-border p-3 sm:p-4"
        >
          <Skeleton className="size-8 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-64" />
          </div>
          <Skeleton className="hidden h-4 w-40 sm:block" />
        </div>
      ))}
    </div>
  );
}
