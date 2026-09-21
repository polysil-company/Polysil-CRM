"use client";

import { Cancel01Icon, Link01Icon, SentIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { useRef, useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Textarea } from "@/components/ui/textarea";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import { useSendMessage } from "@/features/messages/api/messages.mutations";
import {
  MESSAGE_MAX_LENGTH,
  type SendMessageRequest,
} from "@/features/messages/api/messages.schemas";
import {
  parseShareParam,
  SHARE_PARAM,
  type ShareAttachment,
} from "@/features/messages/lib/share-attachment";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/messages/components/message-composer.tsx",
  dataId: "MSG-003",
});

export interface MessageComposerProps {
  conversationId: string;
  /** Names the field for screen readers: "Message Priya Nair". */
  recipientName: string | null;
  disabled?: boolean;
}

/**
 * MSG-003 · Write and send. Enter sends on a keyboard (Shift + Enter for a new line); on
 * touch screens Enter adds a line and the button sends. A lead shared into the page
 * (`?share=lead:…`) is attached until sent or removed. A failed send puts the text back.
 */
export function MessageComposer({
  conversationId,
  recipientName,
  disabled = false,
}: MessageComposerProps): React.JSX.Element {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [share, setShare] = useQueryState(SHARE_PARAM);
  const attachment = parseShareParam(share);
  const send = useSendMessage(conversationId);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const body = draft.trim();
  const overBy = draft.length - MESSAGE_MAX_LENGTH;
  const canSend = !disabled && body !== "" && overBy <= 0;

  const handleSend = (): void => {
    if (!canSend) {
      return;
    }
    const request: SendMessageRequest = { body, resource: attachment };
    setDraft("");
    setError(null);
    log.info("handleSend", "Sending a message", {
      context: { conversationId, linksRecord: attachment !== null },
    });
    send.mutate(request, {
      onSuccess: () => {
        if (attachment !== null) {
          void setShare(null);
        }
      },
      onError: (sendError) => {
        setDraft((current) => (current === "" ? request.body : current));
        setError(toUserFacingError(sendError).title);
        textareaRef.current?.focus();
      },
    });
  };

  return (
    <form
      noValidate
      className="shrink-0 border-t border-border bg-panel p-3 sm:px-4"
      onSubmit={(event) => {
        event.preventDefault();
        handleSend();
      }}
    >
      {attachment === null ? null : (
        <AttachmentChip
          attachment={attachment}
          onRemove={() => {
            void setShare(null);
          }}
        />
      )}
      {error === null ? null : (
        <p role="alert" className="mb-2 text-xs text-danger">
          {error} Your message is back in the box — try sending it again.
        </p>
      )}
      <div className="flex items-end gap-2">
        <Textarea
          ref={textareaRef}
          value={draft}
          rows={1}
          disabled={disabled}
          aria-label={recipientName === null ? "Message" : `Message ${recipientName}`}
          aria-invalid={overBy > 0 ? true : undefined}
          placeholder="Write a message…"
          className="max-h-40 min-h-10 resize-none"
          onChange={(event) => {
            setDraft(event.target.value);
          }}
          onKeyDown={(event) => {
            const touch = window.matchMedia("(pointer: coarse)").matches;
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing &&
              !touch
            ) {
              event.preventDefault();
              handleSend();
            }
          }}
        />
        <Button type="submit" size="icon-lg" aria-label="Send message" disabled={!canSend}>
          <Icon icon={SentIcon} />
        </Button>
      </div>
      {overBy > 0 ? (
        <p className="mt-1.5 text-2xs text-danger">
          {formatNumber(overBy)} characters over the {formatNumber(MESSAGE_MAX_LENGTH)} limit
        </p>
      ) : (
        <p className="mt-1.5 text-2xs text-subtle-foreground pointer-coarse:hidden">
          Enter to send · Shift + Enter for a new line
        </p>
      )}
    </form>
  );
}

function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: ShareAttachment;
  onRemove: () => void;
}): React.JSX.Element {
  const lead = useQuery(leadDetailQueryOptions(attachment.id));
  const label =
    lead.data === undefined
      ? lead.status === "error"
        ? "This lead couldn't be loaded"
        : "Loading lead…"
      : `${lead.data.customerName} · ${lead.data.code}`;

  return (
    <div className="mb-2 flex w-fit max-w-full items-center gap-2 rounded-lg border border-border bg-card py-1 pr-1 pl-2.5 text-sm shadow-xs">
      <Icon icon={Link01Icon} size="sm" className="shrink-0 text-muted-foreground" />
      <span className={cn("truncate", lead.status === "error" && "text-danger")}>
        <span className="text-muted-foreground">Lead · </span>
        {label}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        aria-label="Remove the linked lead"
        onClick={onRemove}
      >
        <Icon icon={Cancel01Icon} />
      </Button>
    </div>
  );
}
