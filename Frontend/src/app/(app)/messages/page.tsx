import { BubbleChatIcon } from "@hugeicons/core-free-icons";
import type { Metadata } from "next";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";

export const metadata: Metadata = { title: "Messages" };

/** Beside the conversation list on wider screens; phones show the list instead. */
export default function MessagesPage(): React.JSX.Element {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <EmptyState
        icon={BubbleChatIcon}
        title="Choose a conversation"
        description="Pick someone from the list, or start a new message."
      />
    </div>
  );
}
