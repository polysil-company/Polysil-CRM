"use client";

import { BubbleChatAddIcon, UserMultiple02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Avatar, AvatarFallback, getInitials } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useStartConversation } from "@/features/messages/api/messages.mutations";
import { staffDirectoryQueryOptions } from "@/features/messages/api/messages.queries";
import type { Person } from "@/features/messages/api/messages.schemas";
import { describePerson } from "@/features/messages/lib/format-messages";
import {
  parseShareParam,
  SHARE_PARAM,
  toShareParam,
  type ShareAttachment,
} from "@/features/messages/lib/share-attachment";
import { toUserFacingError } from "@/lib/api/error-messages";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/messages/components/new-conversation-dialog.tsx",
  dataId: "MSG-004",
});

/**
 * "New message": opens the dialog, and opens it by itself when a lead was shared into
 * /messages (`?share=lead:…`) so the user only has to pick who to share it with.
 */
export function NewConversationLauncher({
  activeConversationId,
}: {
  activeConversationId: string | null;
}): React.JSX.Element {
  const [share, setShare] = useQueryState(SHARE_PARAM);
  const attachment = parseShareParam(share);
  const [openedByUser, setOpenedByUser] = useState(false);
  const open = openedByUser || (attachment !== null && activeConversationId === null);

  return (
    <NewConversationDialog
      open={open}
      attachment={attachment}
      onOpenChange={(next) => {
        setOpenedByUser(next);
        if (!next && activeConversationId === null && share !== null) {
          void setShare(null);
        }
      }}
      onStarted={() => {
        setOpenedByUser(false);
      }}
    />
  );
}

export interface NewConversationDialogProps {
  open: boolean;
  /** The user opened or dismissed the dialog. */
  onOpenChange: (open: boolean) => void;
  /** A conversation was opened; the page is navigating to it. */
  onStarted: () => void;
  /** A record to carry into the conversation's composer. */
  attachment: ShareAttachment | null;
}

/** MSG-004 · Search the staff directory and open (or start) a conversation. */
export function NewConversationDialog({
  open,
  onOpenChange,
  onStarted,
  attachment,
}: NewConversationDialogProps): React.JSX.Element {
  const router = useRouter();
  const [q, setQ] = useState("");
  const directory = useQuery({ ...staffDirectoryQueryOptions(q), enabled: open });
  const start = useStartConversation();

  const handleSelect = (person: Person): void => {
    if (start.isPending) {
      return;
    }
    log.info("handleSelect", "Opening a conversation", {
      context: { participantId: person.id, sharing: attachment !== null },
    });
    start.mutate(person.id, {
      onSuccess: (conversation) => {
        const shareQuery =
          attachment === null
            ? ""
            : `?${SHARE_PARAM}=${encodeURIComponent(toShareParam(attachment))}`;
        router.push(`/messages/${encodeURIComponent(conversation.id)}${shareQuery}`);
        setQ("");
        onStarted();
      },
      onError: (error) => {
        const view = toUserFacingError(error);
        toast.error("Couldn't open the conversation", { description: view.description });
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Icon icon={BubbleChatAddIcon} />
        New message
      </DialogTrigger>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>New message</DialogTitle>
          <DialogDescription>
            {attachment === null
              ? "Choose a colleague to message."
              : "Choose a colleague to share this lead with."}
          </DialogDescription>
        </DialogHeader>
        <div className="px-5 pb-2">
          <SearchField
            label="Search colleagues"
            value={q}
            placeholder="Name, role or office"
            onSearch={setQ}
            className="md:w-full"
          />
        </div>
        <DialogBody className="min-h-64 pb-4">
          <QueryView
            query={directory}
            pending={<PeopleSkeleton />}
            isEmpty={(people) => people.length === 0}
            empty={
              <EmptyState
                icon={UserMultiple02Icon}
                title={q === "" ? "No colleagues to show" : `No one matches “${q}”`}
                description="Try a first name, a role such as “Dispatch”, or an office."
                className="py-8"
              />
            }
          >
            {(people) => (
              <ul aria-label="Colleagues" className="flex flex-col gap-0.5">
                {people.map((person) => {
                  const opening = start.isPending && start.variables === person.id;
                  return (
                    <li key={person.id}>
                      <button
                        type="button"
                        disabled={start.isPending}
                        aria-busy={opening}
                        onClick={() => {
                          handleSelect(person);
                        }}
                        className="flex w-full items-center gap-3 rounded-lg p-2 text-left focus-ring-inset transition-colors duration-fast hover:bg-accent disabled:cursor-wait"
                      >
                        <Avatar size="md">
                          <AvatarFallback>{getInitials(person.name)}</AvatarFallback>
                        </Avatar>
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="truncate text-sm font-medium text-foreground">
                            {person.name}
                          </span>
                          <span className="truncate text-xs text-muted-foreground">
                            {describePerson(person)}
                          </span>
                        </span>
                        {opening ? (
                          <span className="shrink-0 text-xs text-muted-foreground">Opening…</span>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </QueryView>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

function PeopleSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading colleagues" className="flex flex-col gap-0.5">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex items-center gap-3 p-2">
          <Skeleton className="size-8 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-3 w-44" />
          </div>
        </div>
      ))}
    </div>
  );
}
