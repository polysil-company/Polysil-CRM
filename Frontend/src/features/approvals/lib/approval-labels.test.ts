import { describe, expect, it } from "vitest";

import { missingRemarkMessage } from "./approval-labels";

describe("[APPR-001] missingRemarkMessage", () => {
  it("asks a return for its reason, and an Accounts approval for its payment check", () => {
    expect(missingRemarkMessage("reject", "district_manager")).toBe(
      "Say why. The person who asked reads it.",
    );
    expect(missingRemarkMessage("approve", "account_manager")).toBe(
      "Note the payment check: what was received or agreed.",
    );
    expect(missingRemarkMessage("approve", "state_manager")).toBeNull();
  });
});
