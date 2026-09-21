"use client";

import { Alert02Icon, Copy01Icon, RefreshIcon, Tick02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Icon } from "@/components/ui/icon";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { toUserFacingError } from "@/lib/api/error-messages";
import { cn } from "@/lib/utils";

export interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

/**
 * The standard error UI: what happened, what to do, and a copyable reference
 * ("LEAD-001 · 3f2a…") that finds the request in frontend AND backend logs.
 */
export function ErrorState({ error, onRetry, className }: ErrorStateProps): React.JSX.Element {
  const view = toUserFacingError(error);

  return (
    <Empty role="alert" className={className}>
      <EmptyMedia className="text-danger">
        <Icon icon={Alert02Icon} />
      </EmptyMedia>
      <div className="flex flex-col items-center gap-1">
        <EmptyTitle>{view.title}</EmptyTitle>
        <EmptyDescription>{view.description}</EmptyDescription>
      </div>
      {onRetry && view.retryable ? (
        <EmptyContent>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <Icon icon={RefreshIcon} />
            Try again
          </Button>
        </EmptyContent>
      ) : null}
      {view.reference ? <ErrorReference reference={view.reference} /> : null}
    </Empty>
  );
}

export interface ErrorReferenceProps {
  reference: string;
  className?: string;
}

export function ErrorReference({ reference, className }: ErrorReferenceProps): React.JSX.Element {
  const { copied, copy } = useCopyToClipboard();

  return (
    <div
      className={cn(
        "flex max-w-full items-center gap-2 rounded-md border border-border bg-muted py-0.5 pr-0.5 pl-2.5",
        className,
      )}
    >
      <span className="text-2xs font-medium tracking-wider text-subtle-foreground uppercase">
        Ref
      </span>
      <code className="truncate font-mono text-xs text-muted-foreground">{reference}</code>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={copied ? "Reference copied" : "Copy reference"}
        onClick={() => {
          void copy(reference);
        }}
      >
        <Icon icon={copied ? Tick02Icon : Copy01Icon} />
      </Button>
    </div>
  );
}
