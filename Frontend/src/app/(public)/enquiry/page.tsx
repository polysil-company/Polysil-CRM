import type { Metadata } from "next";
import type * as React from "react";

import { EnquiryPage } from "@/features/lead-capture/components/enquiry-form";

export const metadata: Metadata = {
  title: "Enquire about irrigation",
  description: "Ask Polysil about drip and sprinkler irrigation. Our officer calls you back.",
};

/** LEAD-014 · The public enquiry page; `?qr=CODE` when a printed code opened it. No sign-in. */
export default async function EnquiryRoute({
  searchParams,
}: PageProps<"/enquiry">): Promise<React.JSX.Element> {
  const { qr } = await searchParams;
  return <EnquiryPage qr={typeof qr === "string" && qr !== "" ? qr : null} />;
}
