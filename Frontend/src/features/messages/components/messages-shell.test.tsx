import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { sessionKeys } from "@/features/session/api/session.queries";
import { meResponseSchema } from "@/features/session/api/session.schemas";
import { mockMeFor } from "@/mocks/data/sessions";
import { createTestQueryClient, renderWithProviders } from "@/test/render";

import { MessagesShell } from "./messages-shell";

vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: () => null,
  useRouter: () => ({ push: vi.fn() }),
}));

describe("[MSG-001] MessagesShell", () => {
  it("lists a staff member's conversations", async () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(sessionKeys.current(), meResponseSchema.parse(mockMeFor("employee")));
    renderWithProviders(
      <MessagesShell>
        <p>Choose a conversation</p>
      </MessagesShell>,
      { queryClient },
    );

    expect(await screen.findByRole("navigation", { name: "Conversations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Priya Nair/ })).toBeInTheDocument();
  });

  it("tells partner users that messages are for staff", () => {
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(sessionKeys.current(), meResponseSchema.parse(mockMeFor("dealer")));
    renderWithProviders(
      <MessagesShell>
        <p>Choose a conversation</p>
      </MessagesShell>,
      { queryClient },
    );

    expect(screen.getByText("Messages are for Polysil staff")).toBeInTheDocument();
    expect(screen.queryByText("Choose a conversation")).not.toBeInTheDocument();
  });
});
