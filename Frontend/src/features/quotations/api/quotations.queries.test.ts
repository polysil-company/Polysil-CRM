import { describe, expect, it } from "vitest";

import { orderDetailQueryOptions } from "@/features/orders/api/orders.queries";

import { publicQuotationQueryOptions, quotationDetailQueryOptions } from "./quotations.queries";

describe("[QUOT-002] PDF polls in a background tab", () => {
  it("keeps checking while the tab is hidden, so Open PDF is there on return (F-14)", () => {
    expect(quotationDetailQueryOptions("q-1").refetchIntervalInBackground).toBe(true);
    expect(publicQuotationQueryOptions("token").refetchIntervalInBackground).toBe(true);
    expect(orderDetailQueryOptions("o-1").refetchIntervalInBackground).toBe(true);
  });
});
