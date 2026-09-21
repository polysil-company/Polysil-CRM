"use client";

import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { AnimatePresence, motion } from "motion/react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { formatNumber } from "@/lib/format";
import { DURATION, EASE } from "@/lib/motion/tokens";

export interface SelectionBarProps {
  count: number;
  /** Aggregate for the selection, e.g. "₹12.5 L pipeline". */
  summary?: React.ReactNode;
  actions?: React.ReactNode;
  onClear: () => void;
}

/**
 * Floating bar for bulk actions. Rises in when rows are selected; the
 * aggregate tells the user what their selection adds up to.
 */
export function SelectionBar({
  count,
  summary,
  actions,
  onClear,
}: SelectionBarProps): React.JSX.Element {
  return (
    <AnimatePresence>
      {count > 0 ? (
        <motion.div
          key="selection-bar"
          role="region"
          aria-label="Selected rows"
          initial={{ opacity: 0, transform: "translateY(12px) scale(0.98)" }}
          animate={{ opacity: 1, transform: "translateY(0px) scale(1)" }}
          exit={{ opacity: 0, transform: "translateY(12px) scale(0.98)" }}
          transition={{ duration: DURATION.base, ease: EASE.out }}
          className="fixed inset-x-3 bottom-4 layer-toast flex items-center gap-3 rounded-xl border border-border bg-popover py-2 pr-2 pl-4 text-sm text-popover-foreground shadow-lg sm:inset-x-auto sm:left-1/2 sm:min-w-md sm:-translate-x-1/2"
        >
          <span className="font-medium whitespace-nowrap text-foreground tabular-nums">
            {formatNumber(count)} selected
          </span>
          {summary ? (
            <span className="hidden truncate text-muted-foreground sm:inline">{summary}</span>
          ) : null}
          <span className="ml-auto flex items-center gap-1">
            {actions}
            <Button variant="ghost" size="icon-sm" aria-label="Clear selection" onClick={onClear}>
              <Icon icon={Cancel01Icon} />
            </Button>
          </span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
