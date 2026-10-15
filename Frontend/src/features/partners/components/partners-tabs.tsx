"use client";

import type * as React from "react";

import { NavTabs } from "@/components/patterns/nav-tabs";

/** CHNL-001, CHNL-007 · Partners · Dealer applications. */
export function PartnersTabs(): React.JSX.Element {
  return (
    <NavTabs
      tabs={[
        { href: "/partners", label: "Partners" },
        { href: "/partners/applications", label: "Dealer applications" },
      ]}
      label="Channel partners"
      indicatorId="partners-tabs-indicator"
    />
  );
}
