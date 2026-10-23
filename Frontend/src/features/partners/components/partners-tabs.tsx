"use client";

import type * as React from "react";

import { NavTabs } from "@/components/patterns/nav-tabs";
import { useIsStaff } from "@/features/session/hooks/use-session";

/** CHNL-001, CHNL-007 · Partners · Dealer applications. Recruitment is staff only. */
export function PartnersTabs(): React.JSX.Element | null {
  const staff = useIsStaff();
  if (!staff) return null;
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
