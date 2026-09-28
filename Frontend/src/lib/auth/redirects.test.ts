import { describe, expect, it } from "vitest";

import { decideAuthRedirect, safeNextPath, signInPath } from "./redirects";

describe("[AUTH-006] safeNextPath", () => {
  it("keeps a same-site path with its query and hash", () => {
    expect(safeNextPath("/leads?status=won#top")).toBe("/leads?status=won#top");
  });

  it.each([
    ["an absolute URL", "https://evil.example/leads"],
    ["a protocol-relative URL", "//evil.example"],
    ["a backslash, which browsers read as a slash", "/\\evil.example"],
    ["a relative path", "leads"],
    ["a control character", "/leads\n"],
    ["the sign-in page itself", "/sign-in?next=%2Fleads"],
    ["an empty value", ""],
    ["a very long value", `/${"a".repeat(600)}`],
  ])("refuses %s", (_label, value) => {
    expect(safeNextPath(value)).toBeNull();
  });

  it("refuses a missing value", () => {
    expect(safeNextPath(null)).toBeNull();
    expect(safeNextPath(undefined)).toBeNull();
  });
});

describe("[AUTH-006] signInPath", () => {
  it("links to the plain sign-in page by default", () => {
    expect(signInPath()).toBe("/sign-in");
  });

  it("remembers where the visitor was going and why they are signing in", () => {
    expect(signInPath({ next: "/leads?q=patel", reason: "session-ended" })).toBe(
      "/sign-in?next=%2Fleads%3Fq%3Dpatel&reason=session-ended",
    );
  });

  it("leaves out the home page and anything unsafe", () => {
    expect(signInPath({ next: "/dashboard" })).toBe("/sign-in");
    expect(signInPath({ next: "/" })).toBe("/sign-in");
    expect(signInPath({ next: "https://evil.example", reason: "signed-out" })).toBe(
      "/sign-in?reason=signed-out",
    );
  });
});

describe("[AUTH-006] decideAuthRedirect", () => {
  it("sends a signed-out visitor to sign-in, remembering the page", () => {
    expect(decideAuthRedirect({ pathname: "/leads", search: "?page=2", hasSession: false })).toBe(
      "/sign-in?next=%2Fleads%3Fpage%3D2",
    );
    expect(decideAuthRedirect({ pathname: "/", search: "", hasSession: false })).toBe("/sign-in");
  });

  it("lets anyone open a customer's quotation link, signed in or not", () => {
    expect(
      decideAuthRedirect({ pathname: "/q/Xk2p9aQ", search: "", hasSession: false }),
    ).toBeNull();
    expect(decideAuthRedirect({ pathname: "/q/Xk2p9aQ", search: "", hasSession: true })).toBeNull();
    // Only the link itself: "/q" and look-alikes still need a session.
    expect(decideAuthRedirect({ pathname: "/quotations", search: "", hasSession: false })).toBe(
      "/sign-in?next=%2Fquotations",
    );
  });

  it("lets a signed-out visitor open the sign-in page", () => {
    expect(decideAuthRedirect({ pathname: "/sign-in", search: "", hasSession: false })).toBeNull();
  });

  it("sends a signed-in visitor from sign-in to where they were going, or home", () => {
    expect(
      decideAuthRedirect({ pathname: "/sign-in", search: "?next=%2Fleads", hasSession: true }),
    ).toBe("/leads");
    expect(
      decideAuthRedirect({
        pathname: "/sign-in",
        search: "?next=https%3A%2F%2Fevil.example",
        hasSession: true,
      }),
    ).toBe("/dashboard");
  });

  it("lets a signed-in visitor through everywhere else", () => {
    expect(decideAuthRedirect({ pathname: "/leads", search: "", hasSession: true })).toBeNull();
  });
});
