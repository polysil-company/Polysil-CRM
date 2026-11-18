import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { EditPerson } from "@/features/users/components/person-pages";

export const metadata: Metadata = { title: "Edit person" };

/** ADMN-004 · Correct a person's details, role, office or territories. */
export default async function EditPersonPage({
  params,
}: PageProps<"/users/[userId]/edit">): Promise<React.JSX.Element> {
  const { userId } = await params;
  return (
    <PageTransition>
      <PageContainer>
        <EditPerson userId={userId} />
      </PageContainer>
    </PageTransition>
  );
}
