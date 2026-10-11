"use client";

import { ArrowLeft01Icon, BubbleChatIcon } from "@hugeicons/core-free-icons";
import { useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import { useEffect, useRef } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { buttonVariants } from "@/components/ui/button-variants";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarkConversationRead } from "@/features/messages/api/messages.mutations";
import {
  conversationListQueryOptions,
  conversationMessagesQueryOptions,
  messageKeys,
  startedConversationQueryOptions,
} from "@/features/messages/api/messages.queries";
import {
  sendMessageRequestSchema,
  type Conversation,
  type Message,
} from "@/features/messages/api/messages.schemas";
import {
  continuesGroup,
  describePerson,
  formatDayLabel,
} from "@/features/messages/lib/format-messages";
import { useSession } from "@/features/session/hooks/use-session";
import { useNow } from "@/hooks/use-now";
import { isApiError } from "@/lib/api/errors";
import { isSameDay } from "@/lib/format";
import { cn } from "@/lib/utils";

import { MessageBubble } from "./message-bubble";
import { MessageComposer } from "./message-composer";

/**
 * MSG-002 · One conversation: who it is with, the messages grouped by day, and the
 * composer. Unread messages are marked as read while the conversation is open.
 * An unknown conversation renders the not-found page.
 */
export function ConversationThread({
  conversationId,
}: {
  conversationId: string;
}): React.JSX.Element {
  const { data: session } = useSession();
  const queryClient = useQueryClient();
  const thread = useQuery(conversationMessagesQueryOptions(conversationId));
  const conversations = useQuery(conversationListQueryOptions());
  const started = useQuery(startedConversationQueryOptions(conversationId));
  const { mutate: markConversationRead } = useMarkConversationRead();

  // A conversation nobody has written in yet is not listed: the "start" answer names it.
  const conversation =
    conversations.data?.items.find((item) => item.id === conversationId) ?? started.data ?? null;
  const unreadCount = conversation?.unreadCount ?? 0;
  const newestShown = thread.data?.items.at(-1)?.id ?? null;
  const participantLeft = conversation?.participant.isActive === false;

  const pendingBodies = useMutationState({
    filters: { mutationKey: [...messageKeys.all, "send", conversationId], status: "pending" },
    select: (mutation) => {
      const parsed = sendMessageRequestSchema.safeParse(mutation.state.variables);
      return parsed.success ? parsed.data.body : null;
    },
  }).filter((body): body is string => body !== null);

  // Opening the conversation, or new messages arriving while it is open, reads them, up to the
  // newest one on screen: a message that lands meanwhile stays unread (MSG-005, `up_to`).
  useEffect(() => {
    if (unreadCount > 0 && newestShown !== null) {
      markConversationRead({ conversationId, upTo: newestShown });
    }
  }, [conversationId, unreadCount, newestShown, markConversationRead]);

  if (thread.status === "error" && isApiError(thread.error) && thread.error.status === 404) {
    notFound();
  }

  const participantName = conversation?.participant.name ?? null;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <ThreadHeader conversation={conversation} loading={conversations.status === "pending"} />
      <div className="flex min-h-0 flex-1 flex-col">
        <QueryView
          query={thread}
          pending={<MessageLogSkeleton />}
          isEmpty={(page) => page.items.length === 0 && pendingBodies.length === 0}
          empty={
            <div className="flex flex-1 items-center justify-center p-6">
              <EmptyState
                icon={BubbleChatIcon}
                title={
                  participantName === null ? "No messages yet" : `Say hello to ${participantName}`
                }
                description="Write below. You can share a lead from its page to talk about it here."
              />
            </div>
          }
        >
          {(page) => (
            <MessageLog
              messages={page.items}
              pendingBodies={pendingBodies}
              myId={session?.user.id ?? null}
              participantName={participantName ?? "Colleague"}
            />
          )}
        </QueryView>
      </div>
      <MessageComposer
        conversationId={conversationId}
        recipientName={participantName}
        disabled={thread.status !== "success"}
        closedNotice={
          participantLeft
            ? `${participantName ?? "This colleague"} has left Polysil. The conversation stays here to read; new messages can't be sent.`
            : null
        }
        onParticipantLeft={() => {
          void queryClient.invalidateQueries({ queryKey: messageKeys.conversations() });
        }}
      />
    </div>
  );
}

function ThreadHeader({
  conversation,
  loading,
}: {
  conversation: Conversation | null;
  loading: boolean;
}): React.JSX.Element {
  return (
    <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-2 sm:px-4">
      <Link
        href="/messages"
        aria-label="All conversations"
        className={cn(buttonVariants({ variant: "ghost", size: "icon-md" }), "md:hidden")}
      >
        <Icon icon={ArrowLeft01Icon} />
      </Link>
      {conversation === null ? (
        loading ? (
          <div role="status" aria-label="Loading conversation" className="flex items-center gap-3">
            <Skeleton className="size-10 rounded-full" />
            <div className="flex flex-col gap-1.5">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ) : (
          <h2 className="text-sm font-semibold text-foreground">Conversation</h2>
        )
      ) : (
        <>
          <Avatar size="lg">
            <AvatarFallback>{getInitials(conversation.participant.name)}</AvatarFallback>
          </Avatar>
          <div className="flex min-w-0 flex-col">
            <h2 className="truncate text-sm font-semibold text-foreground">
              {conversation.participant.name}
            </h2>
            <p className="truncate text-xs text-muted-foreground">
              {describePerson(conversation.participant)}
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function MessageLog({
  messages,
  pendingBodies,
  myId,
  participantName,
}: {
  messages: readonly Message[];
  pendingBodies: readonly string[];
  myId: string | null;
  participantName: string;
}): React.JSX.Element {
  const now = new Date(useNow());
  const endRef = useRef<HTMLDivElement>(null);
  const lastId = messages.at(-1)?.id;
  const pendingCount = pendingBodies.length;

  // Keep the newest message in view as messages arrive or are sent.
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [lastId, pendingCount]);

  return (
    <div
      role="log"
      aria-label="Messages"
      className="min-h-0 flex-1 scrollbar-thin overflow-y-auto px-3 pt-2 pb-4 sm:px-6"
    >
      <ol className="flex flex-col">
        {messages.map((message, index) => {
          const previous = messages[index - 1];
          const newDay =
            previous === undefined || !isSameDay(previous.createdAt, message.createdAt);
          const mine = message.senderId === myId;
          return (
            <li key={message.id} className="flex flex-col">
              {newDay ? (
                <div className="my-3 flex items-center gap-3 text-xs text-subtle-foreground">
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                  <time dateTime={message.createdAt} suppressHydrationWarning>
                    {formatDayLabel(message.createdAt, now)}
                  </time>
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                </div>
              ) : null}
              <MessageBubble
                body={message.body}
                resource={message.resource}
                createdAt={message.createdAt}
                mine={mine}
                senderName={participantName}
                grouped={continuesGroup(previous, message)}
                showTime={!continuesGroup(message, messages[index + 1])}
              />
            </li>
          );
        })}
        {pendingBodies.map((body, index) => (
          <li key={`pending-${String(index)}`} className="flex flex-col">
            <MessageBubble
              body={body}
              resource={null}
              createdAt={null}
              mine
              senderName="You"
              grouped={false}
              showTime={false}
            />
          </li>
        ))}
      </ol>
      <div ref={endRef} />
    </div>
  );
}

function MessageLogSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading messages"
      className="flex flex-1 flex-col gap-3 px-3 py-4 sm:px-6"
    >
      {["w-56", "w-40", "w-64", "w-32"].map((width, index) => (
        <Skeleton
          key={width}
          className={cn("h-9 rounded-2xl", width, index % 2 === 1 && "self-end")}
        />
      ))}
    </div>
  );
}

/** Route-level fallback while the conversation page loads. */
export function ConversationThreadSkeleton(): React.JSX.Element {
  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4">
        <Skeleton className="size-10 rounded-full" />
        <Skeleton className="h-3.5 w-32" />
      </div>
      <MessageLogSkeleton />
    </div>
  );
}
