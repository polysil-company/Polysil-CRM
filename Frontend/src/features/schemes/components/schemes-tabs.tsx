"use client";

import type * as React from "react";

import { NavTabs } from "@/components/patterns/nav-tabs";

/** SCHM-001, SCHM-004 · Schemes · Credits. */
export function SchemesTabs(): React.JSX.Element {
  return (
    <NavTabs
      tabs={[
        { href: "/schemes", label: "Schemes" },
        { href: "/schemes/credits", label: "Credits" },
      ]}
      label="Schemes"
      indicatorId="schemes-tabs-indicator"
    />
  );
}
