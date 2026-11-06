"use client";

import {
  ArrowLeft01Icon,
  Delete02Icon,
  Edit02Icon,
  LockPasswordIcon,
  Logout03Icon,
  MoreHorizontalIcon,
  SquareUnlock02Icon,
  UserBlock01Icon,
  UserCheck01Icon,
  UserSwitchIcon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound, useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import {
  useDeleteUser,
  usePatchUser,
  useRevokeSessions,
  useUnlockUser,
} from "@/features/users/api/users.mutations";
import { userDetailQueryOptions } from "@/features/users/api/users.queries";
import type { UserDetail } from "@/features/users/api/users.schemas";
import { anchorOf, mobileText, USER_TYPE_LABELS } from "@/features/users/lib/user-labels";
import { useNow } from "@/hooks/use-now";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ConfirmDialog, HandoverDialog, TemporaryPasswordDialog } from "./person-dialogs";

type DialogKind =
  "password" | "revoke" | "unlock" | "deactivate" | "reactivate" | "handover" | "delete";

/**
 * ADMN-002 · One person: how they sign in and whether they can now, their role, office or
 * partner and territories, their open leads, and who added them. An administrator corrects
 * them, sets a temporary password, signs them out, unlocks them, hands their work over,
 * deactivates or deletes them. On your own row only your details can change: the backend
 * refuses the rest, so it isn't offered.
 */
export function PersonDetail({ userId }: { userId: string }): React.JSX.Element {
  const query = useQuery(userDetailQueryOptions(userId));

  if (query.status === "pending") return <PersonDetailSkeleton />;
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 404) notFound();
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <PersonView user={query.data} />;
}

function Item({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm wrap-break-word text-foreground">{children}</dd>
    </div>
  );
}

function Missing({ text }: { text: string }): React.JSX.Element {
  return <span className="text-subtle-foreground">{text}</span>;
}

function PersonView({ user }: { user: UserDetail }): React.JSX.Element {
  const router = useRouter();
  const session = useSession();
  const now = useNow();
  const canEdit = useCan("users", "edit");
  const canDelete = useCan("users", "delete");
  const patch = usePatchUser();
  const revoke = useRevokeSessions();
  const unlock = useUnlockUser();
  const remove = useDeleteUser();
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const close = (): void => {
    setDialog(null);
  };

  const isSelf = session.data?.user.id === user.id;
  const staff = user.userType === "staff";
  const locked = user.lockedUntil !== null && Date.parse(user.lockedUntil) > now;
  const openLeads = user.openLeads ?? 0;
  const deleted = user.deletedAt !== null;
  const role = user.role?.name ?? USER_TYPE_LABELS[user.userType];

  return (
    <article aria-label={user.name} className="flex flex-col gap-4">
      <Link
        href="/users"
        className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "self-start")}
      >
        <Icon icon={ArrowLeft01Icon} />
        Users &amp; roles
      </Link>

      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <Avatar size="lg">
            <AvatarFallback>{getInitials(user.name)}</AvatarFallback>
          </Avatar>
          <div className="flex min-w-0 flex-col gap-1">
            <h1 className="text-xl font-semibold text-foreground">{user.name}</h1>
            <p className="text-sm text-muted-foreground">
              {role} · {anchorOf(user)}
            </p>
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="neutral">{USER_TYPE_LABELS[user.userType]}</Badge>
              {deleted ? (
                <Badge variant="danger" dot>
                  Deleted
                </Badge>
              ) : user.active ? (
                <Badge variant="success" dot>
                  Active
                </Badge>
              ) : (
                <Badge variant="neutral" dot>
                  Deactivated
                </Badge>
              )}
              {user.mustChangePassword && !deleted ? (
                <Badge variant="warning">Temporary password</Badge>
              ) : null}
              {locked ? <Badge variant="danger">Locked out</Badge> : null}
              {isSelf ? <Badge variant="info">You</Badge> : null}
            </div>
          </div>
        </div>

        {canEdit && !deleted ? (
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={`/users/${user.id}/edit`}
              className={buttonVariants({ variant: "outline" })}
            >
              <Icon icon={Edit02Icon} />
              Edit
            </Link>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button variant="outline" aria-label={`More actions for ${user.name}`} />}
              >
                <Icon icon={MoreHorizontalIcon} />
                More
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                {staff ? (
                  <DropdownMenuItem
                    onClick={() => {
                      setDialog("password");
                    }}
                  >
                    <Icon icon={LockPasswordIcon} />
                    Set a temporary password
                  </DropdownMenuItem>
                ) : null}
                {staff && locked ? (
                  <DropdownMenuItem
                    onClick={() => {
                      setDialog("unlock");
                    }}
                  >
                    <Icon icon={SquareUnlock02Icon} />
                    Unlock sign-in
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem
                  onClick={() => {
                    setDialog("revoke");
                  }}
                >
                  <Icon icon={Logout03Icon} />
                  Sign out everywhere
                </DropdownMenuItem>
                {staff ? (
                  <DropdownMenuItem
                    onClick={() => {
                      setDialog("handover");
                    }}
                  >
                    <Icon icon={UserSwitchIcon} />
                    Hand over leads and tasks
                  </DropdownMenuItem>
                ) : null}
                {isSelf ? null : (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => {
                        setDialog(user.active ? "deactivate" : "reactivate");
                      }}
                    >
                      <Icon icon={user.active ? UserBlock01Icon : UserCheck01Icon} />
                      {user.active ? "Deactivate" : "Reactivate"}
                    </DropdownMenuItem>
                    {canDelete ? (
                      <DropdownMenuItem
                        variant="destructive"
                        disabled={openLeads > 0}
                        onClick={() => {
                          setDialog("delete");
                        }}
                      >
                        <Icon icon={Delete02Icon} />
                        {openLeads > 0 ? "Delete (hand over leads first)" : "Delete"}
                      </DropdownMenuItem>
                    ) : null}
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ) : null}
      </header>

      {deleted ? (
        <p role="note" className="rounded-xl border border-danger/40 bg-danger-soft p-3 text-sm">
          Deleted {formatDateTime(user.deletedAt)}. The record stays for the audit trail and the
          leads they created.
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle level={2}>Sign-in</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <Item label={staff ? "Work email" : "Mobile (signs in by code)"}>
                {staff
                  ? (user.email ?? <Missing text="No email" />)
                  : (mobileText(user.mobile) ?? <Missing text="No mobile" />)}
              </Item>
              {staff ? (
                <Item label="Mobile">
                  {mobileText(user.mobile) ?? <Missing text="Not recorded" />}
                </Item>
              ) : null}
              <Item label="Last signed in">
                {user.lastLoginAt === null ? (
                  <Missing text="Never" />
                ) : (
                  <RelativeDate value={user.lastLoginAt} />
                )}
              </Item>
              {staff ? (
                <Item label="Password">
                  {user.mustChangePassword
                    ? "Temporary: they choose their own at the next sign-in"
                    : user.passwordChangedAt === null
                      ? "Set"
                      : `Changed ${formatDateTime(user.passwordChangedAt)}`}
                </Item>
              ) : null}
              {staff && locked && user.lockedUntil !== null ? (
                <Item label="Locked out">
                  Until {formatDateTime(user.lockedUntil)}: five wrong passwords in fifteen minutes.
                </Item>
              ) : null}
              {user.activeSessions === null ? null : (
                <Item label="Live sessions">
                  {user.activeSessions === 0
                    ? "None"
                    : `${String(user.activeSessions)} device${user.activeSessions === 1 ? "" : "s"}`}
                </Item>
              )}
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle level={2}>Role and place</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <Item label="Role">{role}</Item>
              <Item label={staff ? "Office" : "Partner"}>{anchorOf(user)}</Item>
              {staff ? (
                <Item label="Territories" className="sm:col-span-2">
                  {user.territories.length === 0 ? (
                    <Missing text="None" />
                  ) : (
                    <ul aria-label="Territories" className="flex flex-wrap gap-1.5">
                      {user.territories.map((territory) => (
                        <li key={territory.id}>
                          <Badge variant="neutral">{territory.name}</Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                </Item>
              ) : null}
              {user.openLeads === null ? null : (
                <Item label="Open leads">{openLeads === 0 ? "None" : String(openLeads)}</Item>
              )}
              <Item label="Added">
                {formatDateTime(user.createdAt)}
                {user.createdBy === null ? "" : ` by ${user.createdBy.name}`}
              </Item>
            </dl>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent size={dialog === "handover" || dialog === "password" ? "md" : "sm"}>
          {dialog === "password" ? <TemporaryPasswordDialog user={user} onClose={close} /> : null}
          {dialog === "handover" ? (
            <HandoverDialog user={user} isSelf={isSelf} onClose={close} />
          ) : null}
          {dialog === "revoke" ? (
            <ConfirmDialog
              title={`Sign ${user.name} out everywhere?`}
              description="Every device they're signed in on stops at its next request. They can sign in again."
              confirmLabel="Sign out everywhere"
              fn="handleRevokeSessions"
              dataId="ADMN-005"
              action={(idempotencyKey) =>
                revoke.mutateAsync({ userId: user.id, idempotencyKey }).then((result) => {
                  toast.success(
                    result.sessionsRevoked === 0
                      ? "No live sessions to end"
                      : `Signed out of ${String(result.sessionsRevoked)} session${result.sessionsRevoked === 1 ? "" : "s"}`,
                  );
                })
              }
              onDone={close}
            />
          ) : null}
          {dialog === "unlock" ? (
            <ConfirmDialog
              title={`Unlock ${user.name}?`}
              description="They can try their password again now, instead of waiting out the fifteen minutes. The failed attempts stay on record."
              confirmLabel="Unlock"
              fn="handleUnlock"
              dataId="ADMN-005"
              action={(idempotencyKey) =>
                unlock.mutateAsync({ userId: user.id, idempotencyKey }).then((result) => {
                  toast.success(result.wasLocked ? "Unlocked" : "They weren't locked out any more");
                })
              }
              onDone={close}
            />
          ) : null}
          {dialog === "deactivate" ? (
            <ConfirmDialog
              title={`Deactivate ${user.name}?`}
              description={
                openLeads > 0
                  ? `They're signed out everywhere and can't sign in. Their ${String(openLeads)} open lead${openLeads === 1 ? "" : "s"} stay theirs: hand them over first if someone should work them.`
                  : "They're signed out everywhere and can't sign in until reactivated."
              }
              confirmLabel="Deactivate"
              destructive
              fn="handleDeactivate"
              dataId="ADMN-004"
              action={(idempotencyKey) =>
                patch
                  .mutateAsync({ userId: user.id, body: { is_active: false }, idempotencyKey })
                  .then(() => {
                    toast.success(`${user.name} is deactivated`);
                  })
              }
              onDone={close}
            />
          ) : null}
          {dialog === "reactivate" ? (
            <ConfirmDialog
              title={`Reactivate ${user.name}?`}
              description={
                staff
                  ? "They can sign in again with their password, into their office if it's open."
                  : "They can sign in again by code, if their partner is active."
              }
              confirmLabel="Reactivate"
              fn="handleReactivate"
              dataId="ADMN-004"
              action={(idempotencyKey) =>
                patch
                  .mutateAsync({ userId: user.id, body: { is_active: true }, idempotencyKey })
                  .then(() => {
                    toast.success(`${user.name} is active again`);
                  })
              }
              onDone={close}
            />
          ) : null}
          {dialog === "delete" ? (
            <ConfirmDialog
              title={`Delete ${user.name}?`}
              description="They're signed out everywhere and leave the list. The record stays for the audit trail and the leads they created; it can't be undone here."
              confirmLabel="Delete"
              destructive
              fn="handleDelete"
              dataId="ADMN-006"
              action={(idempotencyKey) =>
                remove.mutateAsync({ userId: user.id, idempotencyKey }).then(() => {
                  toast.success(`${user.name} is deleted`);
                })
              }
              onDone={() => {
                close();
                router.push("/users");
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </article>
  );
}

export function PersonDetailSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the person" className="flex flex-col gap-4">
      <Skeleton className="h-8 w-32" />
      <div className="flex items-center gap-3">
        <Skeleton className="size-12 rounded-full" />
        <div className="flex flex-col gap-2">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-48 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    </div>
  );
}
