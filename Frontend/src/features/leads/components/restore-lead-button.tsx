"use client";

import Link from "next/link";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useRestoreLead } from "@/features/leads/api/leads.mutations";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { createRequestId } from "@/lib/api/request-id";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/leads/components/restore-lead-button.tsx",
  dataId: "LEAD-020",
});

/**
 * LEAD-020 · Restore, on a row of Deleted leads (BE-033). Shown only to people who may both
 * delete and edit leads, as the backend requires. The lead goes back to the leads list with its
 * owner; the toast links to it.
 */
export function RestoreLeadButton({ lead }: { lead: Lead }): React.JSX.Element | null {
  const mayDelete = useCan("leads", "delete");
  const mayEdit = useCan("leads", "edit");
  const restore = useRestoreLead();
  const action = useAsyncAction({
    action: () => restore.mutateAsync({ leadId: lead.id, idempotencyKey: createRequestId() }),
    logger: log,
    fn: "handleRestoreLead",
    dataId: "LEAD-020",
    onSuccess: (restored) => {
      toast.success("Lead restored", {
        description: (
          <>
            {restored.customerName} is back in the leads list.{" "}
            <Link
              href={`/leads/${restored.id}`}
              className="font-medium text-primary underline underline-offset-4"
            >
              Open it
            </Link>
          </>
        ),
      });
    },
    onError: (error) => {
      const view = toUserFacingError(error);
      toast.error("Lead not restored", { description: view.description });
    },
  });

  if (!mayDelete || !mayEdit) return null;
  return (
    <Button
      variant="outline"
      size="sm"
      aria-label={`Restore ${lead.customerName}`}
      state={action.state}
      loadingLabel="Restoring…"
      successLabel="Restored"
      errorLabel="Try again"
      onClick={() => void action.run()}
    >
      Restore
    </Button>
  );
}
