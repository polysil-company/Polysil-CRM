import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { sessionKeys } from "@/features/session/api/session.queries";
import { meResponseSchema } from "@/features/session/api/session.schemas";
import type { Role } from "@/lib/auth/roles";
import { mockMeFor } from "@/mocks/data/sessions";
import { createTestQueryClient, renderWithProviders } from "@/test/render";

import { RouteGuard } from "./route-guard";

const navigation = vi.hoisted(() => ({ pathname: "/" }));

vi.mock("next/navigation", () => ({
  usePathname: (): string => navigation.pathname,
}));

function openAs(role: Role, pathname: string): void {
  navigation.pathname = pathname;
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(sessionKeys.current(), meResponseSchema.parse(mockMeFor(role)));
  renderWithProviders(
    <RouteGuard>
      <h1>The page itself</h1>
    </RouteGuard>,
    { queryClient },
  );
}

describe("[APP-006] RouteGuard", () => {
  beforeEach(() => {
    navigation.pathname = "/";
  });

  it.each(["/approval-limits", "/qr-codes", "/dispatch", "/leads/duplicates"])(
    "shows a dealer who opens %s by URL that it isn't theirs, not the page (F-8)",
    (path) => {
      openAs("dealer", path);

      expect(
        screen.getByRole("heading", { name: "You don't have access to this page" }),
      ).toBeInTheDocument();
      expect(screen.queryByText("The page itself")).not.toBeInTheDocument();
      // F-17 · Nothing failed, so there is no reference to copy.
      expect(screen.queryByText("Ref")).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Back to the dashboard" })).toHaveAttribute(
        "href",
        "/dashboard",
      );
    },
  );

  it("renders the page for someone who may open it", () => {
    openAs("admin", "/approval-limits");

    expect(screen.getByText("The page itself")).toBeInTheDocument();
  });

  it("renders a dealer's own pages", () => {
    openAs("dealer", "/leads");

    expect(screen.getByText("The page itself")).toBeInTheDocument();
  });
});
