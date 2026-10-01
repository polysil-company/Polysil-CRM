"use client";

import {
  Cancel01Icon,
  Delete02Icon,
  DeliveryTruck01Icon,
  Edit02Icon,
  MoreVerticalIcon,
  PackageRemoveIcon,
  SentIcon,
} from "@hugeicons/core-free-icons";
import { useState } from "react";
import type * as React from "react";

import { PdfLinkButton } from "@/components/patterns/pdf-link-button";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { getOrderPdf } from "@/features/orders/api/orders.api";
import type { Order } from "@/features/orders/api/orders.schemas";
import { useOrderActions } from "@/features/orders/hooks/use-order-actions";
import { createLogger } from "@/lib/logger";

import { OrderActionDialog, type OrderDialog } from "./order-action-dialog";

const log = createLogger({
  file: "features/orders/components/order-actions.tsx",
  dataId: "SO-002",
});

/**
 * SO-002 … SO-004, DISP-002 · The order's actions, by its status and the user's permissions.
 * A draft is edited and submitted; an approved order opens its PDF, and Dispatch records what
 * leaves or closes the rest short. Cancelling and deleting sit in the "more" menu.
 */
export function OrderActions({ order }: { order: Order }): React.JSX.Element {
  const actions = useOrderActions(order);
  const [dialog, setDialog] = useState<OrderDialog | null>(null);
  const hasMore = actions.closeShort || actions.cancel || actions.delete;
  const open = (next: OrderDialog): void => {
    setDialog(next);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {order.approvedAt !== null && order.status !== "cancelled" ? (
        <PdfLinkButton
          getLink={() => getOrderPdf(order.id)}
          pdfState={order.pdfState}
          logger={log}
          dataId="SO-002"
        />
      ) : null}
      {actions.editHeader ? (
        <Button
          variant="outline"
          onClick={() => {
            open({ kind: "edit" });
          }}
        >
          <Icon icon={Edit02Icon} />
          Edit delivery and terms
        </Button>
      ) : null}
      {actions.submit ? (
        <Button
          onClick={() => {
            open({ kind: "submit" });
          }}
        >
          <Icon icon={SentIcon} />
          {order.lastRejection === null ? "Submit for approval" : "Submit again"}
        </Button>
      ) : null}
      {actions.recordDispatch ? (
        <Button
          onClick={() => {
            open({ kind: "dispatch" });
          }}
        >
          <Icon icon={DeliveryTruck01Icon} />
          Record dispatch
        </Button>
      ) : null}

      {hasMore ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button variant="ghost" size="icon-md" aria-label="More actions" />}
          >
            <Icon icon={MoreVerticalIcon} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {actions.closeShort ? (
              <DropdownMenuItem
                onClick={() => {
                  open({ kind: "close-short" });
                }}
              >
                <Icon icon={PackageRemoveIcon} />
                Close short…
              </DropdownMenuItem>
            ) : null}
            {actions.cancel ? (
              <DropdownMenuItem
                variant="destructive"
                onClick={() => {
                  open({ kind: "cancel" });
                }}
              >
                <Icon icon={Cancel01Icon} />
                Cancel order…
              </DropdownMenuItem>
            ) : null}
            {actions.delete ? (
              <DropdownMenuItem
                variant="destructive"
                onClick={() => {
                  open({ kind: "delete" });
                }}
              >
                <Icon icon={Delete02Icon} />
                Delete draft…
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}

      <OrderActionDialog
        order={order}
        dialog={dialog}
        onClose={() => {
          setDialog(null);
        }}
      />
    </div>
  );
}
