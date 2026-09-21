import { describe, expect, it } from "vitest";

import { cn } from "./utils";

describe("[DS-001] cn", () => {
  it("keeps custom type sizes and colours apart", () => {
    expect(cn("text-2xs", "text-danger")).toBe("text-2xs text-danger");
    expect(cn("text-sm", "text-md")).toBe("text-md");
  });

  it("resolves conflicts between our named tokens (last wins)", () => {
    expect(cn("duration-fast", "duration-slow")).toBe("duration-slow");
    expect(cn("layer-modal", "layer-popover")).toBe("layer-popover");
    expect(cn("h-control-sm", "h-control-md")).toBe("h-control-md");
    expect(cn("shadow-xs", "shadow-panel")).toBe("shadow-panel");
    expect(cn("rounded-md", "rounded-xl")).toBe("rounded-xl");
    expect(cn("ease-out", "ease-drawer")).toBe("ease-drawer");
  });

  it("drops falsy values", () => {
    expect(cn("flex", false, undefined, null, "gap-2")).toBe("flex gap-2");
  });
});
