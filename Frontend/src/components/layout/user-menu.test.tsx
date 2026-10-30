import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { sessionKeys } from "@/features/session/api/session.queries";
import { meResponseSchema } from "@/features/session/api/session.schemas";
import { mockMeFor } from "@/mocks/data/sessions";
import { createTestQueryClient, renderWithProviders } from "@/test/render";

import { UserMenu } from "./user-menu";

describe("[AUTH-005] UserMenu", () => {
  it("opens with the account, the mock backend controls and sign-out", async () => {
    const user = userEvent.setup();
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(
      sessionKeys.current(),
      meResponseSchema.parse(mockMeFor("district_manager")),
    );
    renderWithProviders(<UserMenu />, { queryClient });

    await user.click(screen.getByRole("button", { name: "Account menu for Aarav Desai" }));

    expect(await screen.findByText("District Manager · Vadodara District")).toBeInTheDocument();
    expect(screen.getByText("Mock backend")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
  });

  it("[AUTH-007] offers staff a password change, in a dialog", async () => {
    const user = userEvent.setup();
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(
      sessionKeys.current(),
      meResponseSchema.parse(mockMeFor("district_manager")),
    );
    renderWithProviders(<UserMenu />, { queryClient });

    await user.click(screen.getByRole("button", { name: "Account menu for Aarav Desai" }));
    await user.click(await screen.findByRole("menuitem", { name: "Change password" }));

    const dialog = await screen.findByRole("dialog", { name: "Change password" });
    expect(dialog).toHaveTextContent("signed out on every device");
  });

  it("[AUTH-007] offers a dealer no password change: they sign in by code", async () => {
    const user = userEvent.setup();
    const queryClient = createTestQueryClient();
    const dealer = meResponseSchema.parse(mockMeFor("dealer"));
    queryClient.setQueryData(sessionKeys.current(), dealer);
    renderWithProviders(<UserMenu />, { queryClient });

    await user.click(screen.getByRole("button", { name: `Account menu for ${dealer.user.name}` }));

    expect(await screen.findByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Change password" })).not.toBeInTheDocument();
  });
});
