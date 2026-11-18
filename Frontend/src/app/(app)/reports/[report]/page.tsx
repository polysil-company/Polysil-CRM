import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { Skeleton } from "@/components/ui/skeleton";
import { REPORT_NAMES, type ReportName } from "@/features/reports/api/reports.schemas";
import { ReportView } from "@/features/reports/components/report-view";
import { REPORTS } from "@/features/reports/lib/report-catalogue";

function reportNameOf(value: string): ReportName | null {
  return REPORT_NAMES.find((name) => name === value) ?? null;
}

export async function generateMetadata({
  params,
}: PageProps<"/reports/[report]">): Promise<Metadata> {
  const name = reportNameOf((await params).report);
  return { title: name === null ? "Reports" : REPORTS[name].title };
}

/** RPT-002 · One report; its filters are read from the URL. */
export default async function ReportPage({
  params,
}: PageProps<"/reports/[report]">): Promise<React.JSX.Element> {
  const name = reportNameOf((await params).report);
  if (name === null) notFound();
  return (
    <PageTransition>
      <PageContainer>
        <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
          <ReportView name={name} />
        </Suspense>
      </PageContainer>
    </PageTransition>
  );
}
