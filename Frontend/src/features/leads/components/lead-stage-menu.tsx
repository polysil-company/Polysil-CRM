"use client";

import { ArrowDown01Icon } from "@hugeicons/core-free-icons";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { useTransitionLead } from "@/features/leads/api/leads.mutations";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { LEAD_STAGE_LABELS } from "@/features/leads/lib/lead-labels";
import {
  stageActionLabel,
  stageChangeError,
  stageMenuFor,
  type StageAction,
} from "@/features/leads/lib/lead-lifecycle";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { createLogger } from "@/lib/logger";

import { LeadStageDialog, type StageDialogKind } from "./lead-stage-dialog";

const log = createLogger({
  file: "features/leads/components/lead-stage-menu.tsx",
  dataId: "LEAD-007",
});

export interface LeadStageMenuProps {
  lead: Lead;
}

/**
 * LEAD-007 · "Update stage": the moves the lead's stage allows. Contacting and qualifying
 * happen at once, with a toast; winning, losing and reopening ask first. Steps that happen
 * on a quotation are listed but disabled, so the path forward is never a mystery. A lead
 * with nowhere to go — won or merged — shows no menu.
 */
export function LeadStageMenu({ lead }: LeadStageMenuProps): React.JSX.Element | null {
  const [dialog, setDialog] = useState<StageDialogKind | null>(null);
  const transition = useTransitionLead();
  const idempotency = useIdempotencyKey();
  const menu = stageMenuFor(lead.stage);

  const move = useAsyncAction({
    action: (to: "contacted" | "qualified") => {
      const request = {
        to_stage: to,
        expected_stage: lead.stage,
        lost_reason_id: null,
        lost_note: null,
      };
      return transition.mutateAsync({
        leadId: lead.id,
        body: request,
        idempotencyKey: idempotency.keyFor({ leadId: lead.id, ...request }),
      });
    },
    logger: log,
    fn: "handleMoveStage",
    dataId: "LEAD-007",
    onSuccess: (moved) => {
      idempotency.reset();
      toast.success(`Moved to ${LEAD_STAGE_LABELS[moved.stage]}`, {
        description: moved.customerName,
      });
    },
    onError: (error) => {
      const refusal = stageChangeError(error);
      toast.error(refusal.stale ? "The lead has changed" : "Stage not changed", {
        description: refusal.message,
      });
    },
  });

  if (menu.actions.length === 0) {
    return null;
  }

  const choose = (action: StageAction): void => {
    if (action.kind === "move") {
      void move.run(action.to);
      return;
    }
    setDialog(action.kind);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              state={move.state}
              loadingLabel="Updating…"
              successLabel="Updated"
              errorLabel="Not changed"
            />
          }
        >
          Update stage
          <Icon icon={ArrowDown01Icon} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuGroup>
            <DropdownMenuLabel>Now {LEAD_STAGE_LABELS[lead.stage]}</DropdownMenuLabel>
            {menu.actions.map((action) => (
              <DropdownMenuItem
                key={action.kind === "move" ? action.to : action.kind}
                variant={action.kind === "lost" ? "destructive" : "default"}
                disabled={move.isBusy}
                onClick={() => {
                  choose(action);
                }}
              >
                {stageActionLabel(action)}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
          {menu.hint === null ? null : (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled className="flex-col items-start gap-0.5">
                <span>{menu.hint.label}</span>
                <span className="text-xs text-muted-foreground">{menu.hint.reason}</span>
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <LeadStageDialog
        lead={lead}
        kind={dialog}
        onClose={() => {
          setDialog(null);
        }}
      />
    </>
  );
}
