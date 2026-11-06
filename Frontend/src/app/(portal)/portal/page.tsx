import type { Metadata } from "next";
import type * as React from "react";

import { PortalHome } from "@/features/portal/components/portal-home";

export const metadata: Metadata = { title: "Your record" };

/** FARM-001 · A farmer's own enquiries, quotations, orders and complaints. */
export default function PortalPage(): React.JSX.Element {
  return <PortalHome />;
}
