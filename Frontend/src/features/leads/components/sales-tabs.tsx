"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { NavTabs, type NavTab } from "@/components/patterns/nav-tabs";
import { leadSummaryQueryOptions } from "@/features/leads/api/leads.queries";
import { useCan } from "@/features/session/hooks/use-session";

/** Leads · Quotations · Sales orders. Tabs a role cannot use are not shown. */
export function SalesTabs(): React.JSX.Element {
  const canSeeLeads = useCan("leads:view");
  const canSeeQuotations = useCan("quotations:view");
  const { data: summary } = useQuery(leadSummaryQueryOptions());

  const tabs: NavTab[] = [
    ...(canSeeLeads
      ? [{ href: "/leads", label: "Leads", count: summary?.total } satisfies NavTab]
      : []),
    ...(canSeeQuotations ? [{ href: "/quotations", label: "Quotations" } satisfies NavTab] : []),
    { href: "/sales-orders", label: "Sales orders" },
  ];

  return <NavTabs tabs={tabs} label="Sales" indicatorId="sales-tabs-indicator" />;
}
