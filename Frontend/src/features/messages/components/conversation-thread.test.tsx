import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { sessionKeys } from "@/features/session/api/session.queries";
import { meResponseSchema } from "@/features/session/api/session.schemas";
import { mockMeFor } from "@/mocks/data/sessions";
import { resetMockDb } from "@/mocks/db";
import { createTestQueryClient, renderWithProviders } from "@/test/render";

import { ConversationThread } from "./conversation-thread";

vi.mock("next/navigation", () => ({ notFound: vi.fn() }));

describe("[MSG-002] ConversationThread", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("shows the conversation and sends a message with Enter (MSG-003)", async () => {
    const user = userEvent.setup();
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(
      sessionKeys.current(),
      meResponseSchema.parse(mockMeFor("state_manager")),
    );
    renderWithProviders(<ConversationThread conversationId="conv-003" />, { queryClient });

    expect(
      await screen.findByText("Received this morning — the ledger is updated."),
    ).toBeInTheDocument();

    const field = await screen.findByRole("textbox", { name: "Message Sanjay Rao" });
    await user.type(field, "Order released.{Enter}");

    // The field clears at once and a "Sending…" bubble stands in until the server answers.
    expect(field).toHaveValue("");
    await waitFor(() => {
      expect(screen.queryByText("Sending…")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Order released.")).toBeInTheDocument();
  });

  it("does not send an empty message", async () => {
    const user = userEvent.setup();
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(
      sessionKeys.current(),
      meResponseSchema.parse(mockMeFor("state_manager")),
    );
    renderWithProviders(<ConversationThread conversationId="conv-003" />, { queryClient });

    const field = await screen.findByRole("textbox", { name: "Message Sanjay Rao" });
    await user.type(field, "   ");

    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });
});
