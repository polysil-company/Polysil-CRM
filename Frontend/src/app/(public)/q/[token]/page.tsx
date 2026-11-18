import type { Metadata } from "next";
import type * as React from "react";

import { SharedQuotation } from "@/features/quotations/components/shared-quotation";

export const metadata: Metadata = { title: "Your quotation" };

/** QUOT-012 · The link a customer receives with their quotation. No sign-in. */
export default async function SharedQuotationPage({
  params,
}: PageProps<"/q/[token]">): Promise<React.JSX.Element> {
  const { token } = await params;

  return <SharedQuotation token={token} />;
}
