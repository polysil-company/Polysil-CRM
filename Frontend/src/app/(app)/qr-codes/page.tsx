import type { Metadata } from "next";
import type * as React from "react";

import { PageTransition } from "@/components/layout/page-transition";
import { PageContainer } from "@/components/patterns/page-container";
import { QrCodes } from "@/features/lead-capture/components/qr-codes";

export const metadata: Metadata = { title: "QR codes" };

/** LEAD-013 · The title and description sit in the top bar, from the navigation map. */
export default function QrCodesPage(): React.JSX.Element {
  return (
    <PageTransition>
      <PageContainer>
        <QrCodes />
      </PageContainer>
    </PageTransition>
  );
}
