"use client";

import type * as React from "react";

import { NavTabs } from "@/components/patterns/nav-tabs";

/** SUBS-002, SUBS-005, SUBS-009 · Applications · Reports · Calculator. */
export function SubsidyTabs(): React.JSX.Element {
  return (
    <NavTabs
      tabs={[
        { href: "/subsidy", label: "Applications" },
        { href: "/subsidy/reports", label: "Reports" },
        { href: "/subsidy/calculator", label: "Calculator" },
      ]}
      label="Subsidy"
      indicatorId="subsidy-tabs-indicator"
    />
  );
}
