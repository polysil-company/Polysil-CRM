import { act, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { acceptSessionTokens, endSession } from "@/lib/auth/session-store";
import { renderWithProviders } from "@/test/render";

import { AuthGate } from "./auth-gate";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

function renderGate() {
  return renderWithProviders(
    <AuthGate>
      <p>Workspace</p>
    </AuthGate>,
  );
}

/**
 * The session store is one module-level state per page, so these steps run in
 * order through one visit: never signed in → signed in → session ended → signed out.
 */
describe("[AUTH-006] AuthGate", () => {
  beforeAll(() => {
    window.history.replaceState({}, "", "/leads?page=2");
  });

  afterAll(() => {
    window.history.replaceState({}, "", "/");
    document.cookie = "polysil_session=; Max-Age=0; Path=/";
  });

  it("sends a visitor without a session to sign-in, remembering the page", async () => {
    renderGate();

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fleads%3Fpage%3D2");
    });
    expect(screen.queryByText("Workspace")).not.toBeInTheDocument();
  });

  it("shows the page once the tab holds a session", () => {
    acceptSessionTokens({ accessToken: "mock.0.test", expiresInSeconds: 900 });

    renderGate();

    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("drops cached data and returns to sign-in when the session ends", async () => {
    replace.mockClear();
    const { queryClient } = renderGate();
    queryClient.setQueryData(["leads"], ["cached"]);

    act(() => {
      endSession("session-ended");
    });

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith(
        "/sign-in?next=%2Fleads%3Fpage%3D2&reason=session-ended",
      );
    });
    expect(queryClient.getQueryData(["leads"])).toBeUndefined();
    expect(screen.queryByText("Workspace")).not.toBeInTheDocument();
  });

  it("does not offer to return after a deliberate sign-out, and leaves no toast behind", async () => {
    acceptSessionTokens({ accessToken: "mock.0.test", expiresInSeconds: 900 });
    replace.mockClear();
    renderWithProviders(
      <>
        <AuthGate>
          <p>Workspace</p>
        </AuthGate>
        <Toaster />
      </>,
    );
    act(() => {
      toast.success("Order saved");
    });
    expect(await screen.findByText("Order saved")).toBeInTheDocument();

    act(() => {
      endSession("signed-out");
    });

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/sign-in?reason=signed-out");
    });
    await waitFor(() => {
      expect(screen.queryByText("Order saved")).not.toBeInTheDocument();
    });
  });
});
