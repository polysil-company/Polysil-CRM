import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { HelpPage } from "@/features/assistant/components/help-page";

export const metadata: Metadata = { title: "Help" };

/** BOT-002 · The title and description sit in the top bar, from the navigation map. */
export default function HelpRoute(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <HelpPage />
      </PageContainer>
    </PageTransition>
  );
}
