import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { NewPerson } from "@/features/users/components/person-pages";

export const metadata: Metadata = { title: "New person" };

/** ADMN-003 · Add a staff member or a partner user. */
export default function NewPersonPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <NewPerson />
      </PageContainer>
    </PageTransition>
  );
}
