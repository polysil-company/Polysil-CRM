import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  ASSISTANT_LIMIT,
  assistantActionsSchema,
  assistantAnswerSchema,
  type AssistantAction,
  type AssistantAnswer,
} from "./assistant.schemas";

const log = createLogger({ file: "features/assistant/api/assistant.api.ts", dataId: "BOT-001" });

/** BOT-001 · Actions and records for what was typed; an empty `q` gives a starter set. */
export function searchAssistant(q: string, signal?: AbortSignal): Promise<AssistantAnswer> {
  return apiRequest({
    dataId: "BOT-001",
    logger: log,
    fn: "searchAssistant",
    path: "/assistant",
    query: { q, limit: ASSISTANT_LIMIT },
    schema: assistantAnswerSchema,
    signal,
  });
}

/** BOT-002 · Every action the user may take, for the help page. */
export function listAssistantActions(signal?: AbortSignal): Promise<AssistantAction[]> {
  return apiRequest({
    dataId: "BOT-002",
    logger: log,
    fn: "listAssistantActions",
    path: "/assistant/actions",
    schema: assistantActionsSchema,
    signal,
  });
}
