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
});
