import type * as React from "react";

import { QrCodesSkeleton } from "@/features/lead-capture/components/qr-codes";

export default function QrCodesLoading(): React.JSX.Element {
  return <QrCodesSkeleton />;
}
