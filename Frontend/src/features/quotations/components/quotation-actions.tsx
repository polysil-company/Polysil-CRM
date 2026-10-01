"use client";

import {
  ArrowDown01Icon,
  Clock01Icon,
  Delete02Icon,
  Edit02Icon,
  GitBranchIcon,
  MoreVerticalIcon,
  SentIcon,
  UserCheck01Icon,
} from "@hugeicons/core-free-icons";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { PlaceOrder } from "@/features/orders/components/place-order";
import type { Quotation } from "@/features/quotations/api/quotations.schemas";
import { QUOTATION_STATUS_LABELS } from "@/features/quotations/lib/quotation-labels";
import { ANSWER_LABELS, quotationActions } from "@/features/quotations/lib/quotation-lifecycle";
import { useCan } from "@/features/session/hooks/use-session";
import { todayInIndia } from "@/lib/format";

import { QuotationActionDialog, type QuotationDialog } from "./quotation-action-dialog";
import { QuotationPdfButton } from "./quotation-pdf-button";

export interface QuotationActionsProps {
  quotation: Quotation;
}

/**
 * QUOT-003, QUOT-006 … QUOT-011 · The quotation's actions, by its status and the user's
 * permissions. A draft is edited and sent — or, above the owner's discount limit, sent for
 * approval first. A sent quotation records the customer's answer and can be revised; an
 * accepted one is placed as an order (SO-003). A superseded version offers none: its notice
 * links to the version that replaced it.
 */
export function QuotationActions({ quotation }: QuotationActionsProps): React.JSX.Element | null {
  const canEdit = useCan("quotations", "edit");
  const canDelete = useCan("quotations", "delete");
  const [dialog, setDialog] = useState<QuotationDialog | null>(null);
  const actions = quotationActions(quotation, { edit: canEdit, delete: canDelete }, todayInIndia());
  const sent = quotation.status !== "draft";
  const send = actions.draft?.send ?? null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {sent && quotation.pdfState !== null ? (
        <QuotationPdfButton quotationId={quotation.id} pdfState={quotation.pdfState} />
      ) : null}

      {actions.draft?.edit === true ? (
        <Link
          href={`/quotations/${quotation.id}/edit`}
          transitionTypes={["nav-forward"]}
          className={buttonVariants({ variant: "outline" })}
        >
          <Icon icon={Edit02Icon} />
          Edit draft
        </Link>
      ) : null}
      {send?.kind === "send" ? (
        <Button
          onClick={() => {
            setDialog({ kind: "send" });
          }}
        >
          <Icon icon={SentIcon} />
          Send
        </Button>
      ) : null}
      {send?.kind === "request-approval" ? (
        <Button
          onClick={() => {
            setDialog({ kind: "approval", why: send.why });
          }}
        >
          <Icon icon={UserCheck01Icon} />
          Ask for approval
        </Button>
      ) : null}
      {send?.kind === "waiting" ? (
        <Button disabled>
          <Icon icon={Clock01Icon} />
          Waiting for approval
        </Button>
      ) : null}

      {actions.answers.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button />}>
            Record answer
            <Icon icon={ArrowDown01Icon} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuGroup>
              <DropdownMenuLabel>Now {QUOTATION_STATUS_LABELS[quotation.status]}</DropdownMenuLabel>
              {actions.answers.map((answer) => (
                <DropdownMenuItem
                  key={answer}
                  variant={answer === "rejected" ? "destructive" : "default"}
                  onClick={() => {
                    setDialog({ kind: "answer", to: answer });
                  }}
                >
                  {ANSWER_LABELS[answer]}…
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      {actions.revise ? (
        <Button
          variant="outline"
          onClick={() => {
            setDialog({ kind: "revise" });
          }}
        >
          <Icon icon={GitBranchIcon} />
          Revise
        </Button>
      ) : null}

      <PlaceOrder quotation={quotation} />

      {actions.draft?.delete === true ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="ghost" size="icon-md" aria-label="More actions" />}
          >
            <Icon icon={MoreVerticalIcon} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem
              variant="destructive"
              onClick={() => {
                setDialog({ kind: "delete" });
              }}
            >
              <Icon icon={Delete02Icon} />
              Delete draft…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}

      <QuotationActionDialog
        quotation={quotation}
        dialog={dialog}
        onClose={() => {
          setDialog(null);
        }}
      />
    </div>
  );
}
