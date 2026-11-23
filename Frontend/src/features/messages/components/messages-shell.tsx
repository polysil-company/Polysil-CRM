"use client";

import { MessageMultiple01Icon } from "@hugeicons/core-free-icons";
import { useSelectedLayoutSegment } from "next/navigation";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { PageContainer } from "@/components/patterns/page-container";
import { useSession } from "@/features/session/hooks/use-session";
import { cn } from "@/lib/utils";

import { ConversationList } from "./conversation-list";

/**
 * MSG-001 · The Messages area. Desktop and tablet: the conversation list beside the open
 * conversation. Phones: the list, or the conversation — one at a time. Partner users
 * see a notice instead, since messaging is for staff (the backend refuses them too).
 */
export function MessagesShell({ children }: { children: React.ReactNode }): React.JSX.Element {
  const conversationId = useSelectedLayoutSegment();
  const { data: session } = useSession();

  if (session !== undefined && session.userType !== "staff") {
    return (
      <PageContainer>
        <EmptyState
          icon={MessageMultiple01Icon}
          title="Messages are for Polysil staff"
          description="Conversations between colleagues aren't part of partner accounts."
          className="py-16"
        />
      </PageContainer>
    );
  }

  const threadOpen = conversationId !== null;

  return (
    <div className="flex h-full min-h-0">
      <ConversationList
        activeConversationId={conversationId}
        className={cn(
          "w-full md:flex md:w-80 md:shrink-0 md:border-r md:border-border",
          threadOpen ? "hidden" : "flex",
        )}
      />
      <div className={cn("min-w-0 flex-1 flex-col md:flex", threadOpen ? "flex" : "hidden")}>
        {children}
      </div>
    </div>
  );
}
