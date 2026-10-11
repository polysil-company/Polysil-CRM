import type { QueryClient } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { startConversation } from "@/features/messages/api/messages.api";
import { startedConversationQueryOptions } from "@/features/messages/api/messages.queries";
import { sessionKeys } from "@/features/session/api/session.queries";
import { meResponseSchema } from "@/features/session/api/session.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { createTestQueryClient, renderWithProviders } from "@/test/render";

import { ConversationThread } from "./conversation-thread";

vi.mock("next/navigation", () => ({ notFound: vi.fn() }));

function signedInClient(): QueryClient {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(
    sessionKeys.current(),
    meResponseSchema.parse(mockMeFor("state_manager")),
  );
  return queryClient;
}

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

  it("reads the conversation up to the newest message on screen (MSG-005)", async () => {
    let sent: unknown;
    server.use(
      // Notes the body, then falls through to the mock backend's own handler.
      http.post(buildApiUrl("/conversations/:conversationId/read"), async ({ request }) => {
        sent = await request.clone().json();
      }),
    );
    const newest = mockDb.messages
      .filter((message) => message.conversation_id === "conv-001")
      .at(-1);
    renderWithProviders(<ConversationThread conversationId="conv-001" />, {
      queryClient: signedInClient(),
    });

    await waitFor(() => {
      expect(sent).toEqual({ up_to: newest?.id });
    });
  });

  it("keeps a colleague who has left readable, with nothing more to send", async () => {
    renderWithProviders(<ConversationThread conversationId="conv-005" />, {
      queryClient: signedInClient(),
    });

    expect(await screen.findByText("Thanks Meera, all the best.")).toBeInTheDocument();
    expect(await screen.findByText(/Meera Iyer has left Polysil/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Message Meera Iyer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
  });

  it("names a colleague in a conversation just started, before anyone writes (MSG-004)", async () => {
    const queryClient = signedInClient();
    const conversation = await startConversation("usr-007");
    queryClient.setQueryData(
      startedConversationQueryOptions(conversation.id).queryKey,
      conversation,
    );
    renderWithProviders(<ConversationThread conversationId={conversation.id} />, { queryClient });

    expect(await screen.findByRole("heading", { name: "Imran Sheikh" })).toBeInTheDocument();
    expect(await screen.findByText("Say hello to Imran Sheikh")).toBeInTheDocument();
  });

  it("closes the conversation when the backend says the colleague has left, keeping the draft", async () => {
    let left = false;
    server.use(
      http.post(buildApiUrl("/conversations/:conversationId/messages"), () => {
        left = true;
        const conversation = mockDb.conversations.find((item) => item.id === "conv-003");
        if (conversation !== undefined) {
          conversation.participant = { ...conversation.participant, is_active: false };
        }
        return HttpResponse.json(
          {
            error: {
              code: "participant_inactive",
              message: "That colleague has left.",
              fields: { participant: "no longer active" },
            },
          },
          { status: 422 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ConversationThread conversationId="conv-003" />, {
      queryClient: signedInClient(),
    });

    const field = await screen.findByRole("textbox", { name: "Message Sanjay Rao" });
    await user.type(field, "Are you there?{Enter}");

    expect(
      await screen.findByText(/Sanjay Rao has left Polysil, so new messages/),
    ).toBeInTheDocument();
    expect(left).toBe(true);
    // The list is read again and now says so: the box turns read-only, the draft still in it.
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Message Sanjay Rao" })).toHaveAttribute(
        "readonly",
      );
    });
    expect(screen.getByRole("textbox", { name: "Message Sanjay Rao" })).toHaveValue(
      "Are you there?",
    );
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });
});
