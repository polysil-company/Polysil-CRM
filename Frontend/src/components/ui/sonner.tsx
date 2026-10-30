"use client";

import {
  Alert02Icon,
  CheckmarkCircle02Icon,
  InformationCircleIcon,
  MultiplicationSignCircleIcon,
} from "@hugeicons/core-free-icons";
import type * as React from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useTheme } from "@/lib/theme/use-theme";

import { Icon } from "./icon";
import { ProgressRing } from "./spinner";

/**
 * Based on shadcn/ui (base-nova) — reworked: follows our theme store instead
 * of next-themes and is styled with token classes instead of inline styles.
 * Usage: `import { toast } from "sonner"` → toast.success("Lead created").
 */
export function Toaster(props: ToasterProps): React.JSX.Element {
  const { resolvedTheme } = useTheme();

  return (
    <Sonner
      theme={resolvedTheme}
      position="bottom-right"
      gap={8}
      icons={{
        success: <Icon icon={CheckmarkCircle02Icon} className="text-success" />,
        info: <Icon icon={InformationCircleIcon} className="text-info" />,
        warning: <Icon icon={Alert02Icon} className="text-warning" />,
        error: <Icon icon={MultiplicationSignCircleIcon} className="text-danger" />,
        loading: <ProgressRing className="text-muted-foreground" />,
      }}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "flex w-(--width) items-start gap-3 rounded-lg border border-border bg-popover p-3.5 text-sm text-popover-foreground shadow-lg",
          title: "font-medium text-foreground",
          description: "mt-0.5 text-muted-foreground",
          icon: "mt-0.5 flex size-4 items-center justify-center",
          actionButton:
            "press-scale ml-auto h-control-xs shrink-0 rounded-sm bg-primary px-2 text-xs font-medium text-primary-foreground",
          cancelButton:
            "press-scale h-control-xs shrink-0 rounded-sm bg-secondary px-2 text-xs font-medium text-secondary-foreground",
          closeButton: "text-subtle-foreground hover:text-foreground",
        },
      }}
      {...props}
    />
  );
}
