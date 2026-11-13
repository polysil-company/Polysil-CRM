import type * as React from "react";

import { MessagesShell } from "@/features/messages/components/messages-shell";

/** Conversations stay listed while the open conversation changes (MSG-001). */
export default function MessagesLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return <MessagesShell>{children}</MessagesShell>;
}
