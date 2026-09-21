"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { NavTabs, type NavTab } from "@/components/patterns/nav-tabs";
import { leadSummaryQueryOptions } from "@/features/leads/api/leads.queries";
import { useCan } from "@/features/session/hooks/use-session";

/** Leads · Quotations · Sales orders. Tabs the user cannot view are not shown. */
export function SalesTabs(): React.JSX.Element {
  const canSeeLeads = useCan("leads");
  const canSeeQuotations = useCan("quotations");
  const canSeeOrders = useCan("orders");
  const { data: summary } = useQuery(leadSummaryQueryOptions());

  const tabs: NavTab[] = [
    ...(canSeeLeads
      ? [{ href: "/leads", label: "Leads", count: summary?.total } satisfies NavTab]
      : []),
    ...(canSeeQuotations ? [{ href: "/quotations", label: "Quotations" } satisfies NavTab] : []),
    ...(canSeeOrders ? [{ href: "/sales-orders", label: "Sales orders" } satisfies NavTab] : []),
  ];

  return <NavTabs tabs={tabs} label="Sales" indicatorId="sales-tabs-indicator" />;
}
