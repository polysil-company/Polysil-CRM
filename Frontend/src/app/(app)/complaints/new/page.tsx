import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { NewComplaint } from "@/features/complaints/components/complaint-pages";

export const metadata: Metadata = { title: "New complaint" };

/** CMPL-003 · `?lead=` or `?order=` raises it about that lead or order. */
export default async function NewComplaintPage({
  searchParams,
}: PageProps<"/complaints/new">): Promise<React.JSX.Element> {
  const params = await searchParams;
  const one = (value: string | string[] | undefined): string | null =>
    typeof value === "string" && value !== "" ? value : null;

  return (
    <PageTransition>
      <PageContainer>
        <NewComplaint leadId={one(params.lead)} orderId={one(params.order)} />
      </PageContainer>
    </PageTransition>
  );
}
