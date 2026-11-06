import {
  AlertCircleIcon,
  CheckmarkCircle02Icon,
  InformationCircleIcon,
} from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/utils";

export type NoticeTone = "info" | "warning" | "danger" | "success";

const NOTICE_CLASSES: Readonly<Record<NoticeTone, { box: string; icon: string }>> = {
  info: { box: "bg-info-soft", icon: "text-info" },
  warning: { box: "bg-warning-soft", icon: "text-warning" },
  danger: { box: "bg-danger-soft", icon: "text-danger" },
  success: { box: "bg-success-soft", icon: "text-success" },
};

const NOTICE_ICONS = {
  info: InformationCircleIcon,
  success: CheckmarkCircle02Icon,
  warning: AlertCircleIcon,
  danger: AlertCircleIcon,
} as const satisfies Record<NoticeTone, unknown>;

export interface NoticeProps {
  tone: NoticeTone;
  children: React.ReactNode;
  className?: string;
}

/**
 * A notice above a document: what the reader must know before trusting it. The icon and the
 * words carry the meaning, so the tint is never the only signal.
 */
export function Notice({ tone, children, className }: NoticeProps): React.JSX.Element {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-lg border border-border p-3 text-sm text-foreground",
        NOTICE_CLASSES[tone].box,
        className,
      )}
    >
      <Icon icon={NOTICE_ICONS[tone]} className={cn("mt-0.5", NOTICE_CLASSES[tone].icon)} />
      <div className="flex min-w-0 flex-col gap-1">{children}</div>
    </div>
  );
}
