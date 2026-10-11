"use client";

import type * as React from "react";

import { NavTabs } from "@/components/patterns/nav-tabs";

/** SUBS-002, SUBS-005 · Applications · Calculator. */
export function SubsidyTabs(): React.JSX.Element {
  return (
    <NavTabs
      tabs={[
        { href: "/subsidy", label: "Applications" },
        { href: "/subsidy/calculator", label: "Calculator" },
      ]}
      label="Subsidy"
      indicatorId="subsidy-tabs-indicator"
    />
  );
}
