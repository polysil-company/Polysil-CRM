import type { Metadata } from "next";
import { Suspense } from "react";
import type * as React from "react";

import {
  ConversationThread,
  ConversationThreadSkeleton,
} from "@/features/messages/components/conversation-thread";

export const metadata: Metadata = { title: "Messages" };

export default async function ConversationPage({
  params,
}: PageProps<"/messages/[conversationId]">): Promise<React.JSX.Element> {
  const { conversationId } = await params;

  return (
    // The composer reads a shared lead from the URL, which needs a Suspense boundary.
    <Suspense fallback={<ConversationThreadSkeleton />}>
      <ConversationThread conversationId={conversationId} />
    </Suspense>
  );
}
