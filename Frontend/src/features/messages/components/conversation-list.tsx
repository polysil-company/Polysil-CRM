"use client";

import { BubbleChatIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Suspense } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { conversationListQueryOptions } from "@/features/messages/api/messages.queries";
import type { Conversation } from "@/features/messages/api/messages.schemas";
import { formatConversationTime } from "@/features/messages/lib/format-messages";
import { useSession } from "@/features/session/hooks/use-session";
import { useNow } from "@/hooks/use-now";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { NewConversationLauncher } from "./new-conversation-dialog";

export interface ConversationListProps {
  activeConversationId: string | null;
  className?: string;
}

/** MSG-001 · Everyone the user talks to, most recent first, with unread counts. */
export function ConversationList({
  activeConversationId,
  className,
}: ConversationListProps): React.JSX.Element {
  const query = useQuery(conversationListQueryOptions());
  const { data: session } = useSession();
  const myId = session?.user.id ?? null;

  return (
    <div className={cn("min-h-0 flex-col", className)}>
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border px-4">
        <h2 className="text-sm font-semibold text-foreground">Conversations</h2>
        {/* Reading the shared lead from the URL needs a Suspense boundary during prerendering. */}
        <Suspense
          fallback={
            <Button variant="outline" size="sm" disabled>
              New message
            </Button>
          }
        >
          <NewConversationLauncher activeConversationId={activeConversationId} />
        </Suspense>
      </div>
      <div className="min-h-0 flex-1 scrollbar-thin overflow-y-auto">
        <QueryView
          query={query}
          pending={<ConversationListSkeleton />}
          isEmpty={(list) => list.items.length === 0}
          empty={
            <EmptyState
              icon={BubbleChatIcon}
              title="No conversations yet"
              description="Use New message to talk to a colleague — about a lead, an order or anything else."
              className="px-6 py-12"
            />
          }
        >
          {(list) => (
            <nav aria-label="Conversations">
              <ul className="flex flex-col gap-0.5 p-2">
                {list.items.map((conversation) => (
                  <li key={conversation.id}>
                    <ConversationRow
                      conversation={conversation}
                      active={conversation.id === activeConversationId}
                      myId={myId}
                    />
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </QueryView>
      </div>
    </div>
  );
}

function ConversationRow({
  conversation,
  active,
  myId,
}: {
  conversation: Conversation;
  active: boolean;
  myId: string | null;
}): React.JSX.Element {
  const now = new Date(useNow());
  const { participant, lastMessage, unreadCount } = conversation;
  const unread = unreadCount > 0;
  const preview =
    lastMessage === null
      ? "No messages yet"
      : `${lastMessage.senderId === myId ? "You: " : ""}${lastMessage.body}`;

  return (
    <Link
      href={`/messages/${encodeURIComponent(conversation.id)}`}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-lg p-2.5 focus-ring-inset transition-colors duration-fast",
        active ? "bg-accent" : "hover:bg-accent",
      )}
    >
      <Avatar size="lg">
        <AvatarFallback>{getInitials(participant.name)}</AvatarFallback>
      </Avatar>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-baseline justify-between gap-2">
          <span
            className={cn(
              "truncate text-sm text-foreground",
              unread ? "font-semibold" : "font-medium",
            )}
          >
            {participant.name}
          </span>
          <time
            dateTime={conversation.updatedAt}
            suppressHydrationWarning
            className={cn(
              "shrink-0 text-xs tabular-nums",
              unread ? "font-medium text-primary-text" : "text-subtle-foreground",
            )}
          >
            {formatConversationTime(conversation.updatedAt, now)}
          </time>
        </span>
        <span className="flex items-center justify-between gap-2">
          <span
            className={cn("truncate text-sm", unread ? "text-foreground" : "text-muted-foreground")}
          >
            {preview}
          </span>
          {unread ? (
            <Badge size="sm" variant="primary" className="shrink-0 tabular-nums">
              <span className="sr-only">Unread messages: </span>
              {formatNumber(unreadCount)}
            </Badge>
          ) : null}
        </span>
      </span>
    </Link>
  );
}

export function ConversationListSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading conversations" className="flex flex-col gap-0.5 p-2">
      {[0, 1, 2, 3, 4].map((row) => (
        <div key={row} className="flex items-center gap-3 p-2.5">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-3 w-44" />
          </div>
        </div>
      ))}
    </div>
  );
}
