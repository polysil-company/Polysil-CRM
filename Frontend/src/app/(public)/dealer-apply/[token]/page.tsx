import type { Metadata } from "next";
import type * as React from "react";

import { DealerApplyPage } from "@/features/dealer-applications/components/dealer-apply-page";

export const metadata: Metadata = { title: "Dealer application" };

/** CHNL-008 · The link a prospective dealer is sent. No sign-in: the mobile is verified here. */
export default async function DealerApplyRoute({
  params,
}: PageProps<"/dealer-apply/[token]">): Promise<React.JSX.Element> {
  const { token } = await params;

  return <DealerApplyPage token={token} />;
}
