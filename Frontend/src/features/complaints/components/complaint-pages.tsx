"use client";

import { useQuery } from "@tanstack/react-query";
import { notFound } from "next/navigation";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { complaintDetailQueryOptions } from "@/features/complaints/api/complaints.queries";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import { orderDetailQueryOptions } from "@/features/orders/api/orders.queries";
import { isApiError } from "@/lib/api/errors";

import { ComplaintDetailSkeleton } from "./complaint-detail";
import { ComplaintForm } from "./complaint-form";

/** CMPL-003 · A new complaint, about a lead or an order when opened from their pages. */
export function NewComplaint({
  leadId,
  orderId,
}: {
  leadId: string | null;
  orderId: string | null;
}): React.JSX.Element {
  const lead = useQuery({ ...leadDetailQueryOptions(leadId ?? ""), enabled: leadId !== null });
  const order = useQuery({ ...orderDetailQueryOptions(orderId ?? ""), enabled: orderId !== null });
  const label =
    order.data !== undefined
      ? `order ${order.data.orderNo ?? "draft"}`
      : lead.data !== undefined
        ? `${lead.data.customerName} (${lead.data.code})`
        : null;

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold text-foreground">New complaint</h2>
      <ComplaintForm complaint={null} about={{ leadId, orderId, label }} />
    </div>
  );
}

/** CMPL-003 · Edit a draft. Anything else goes back to the complaint's page. */
export function EditComplaint({ complaintId }: { complaintId: string }): React.JSX.Element {
  const query = useQuery(complaintDetailQueryOptions(complaintId));
  if (query.status === "pending") return <ComplaintDetailSkeleton />;
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 404) notFound();
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  const complaint = query.data;
  if (!complaint.can.edit) {
    return (
      <p role="note" className="text-sm text-muted-foreground">
        This complaint is no longer a draft you can edit.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold text-foreground">
        Edit {complaint.number ?? "the draft complaint"}
      </h2>
      <ComplaintForm complaint={complaint} />
    </div>
  );
}
