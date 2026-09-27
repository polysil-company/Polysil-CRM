import { z } from "zod";

import { LEAD_STAGES, type LeadStage } from "@/features/leads/api/leads.schemas";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";

import { LEAD_STAGE_LABELS } from "./lead-labels";

/**
 * LEAD-007 · What the stage menu offers for a lead.
 *
 * Mirrors the backend's stage machine (`TRANSITIONS` in backend/api/domain/leads.py) so
 * the menu only offers moves that can succeed. The backend still decides: a refusal is
 * explained by `stageChangeError`. quoted and negotiation are reached through a
 * quotation, never from here; won needs an accepted quotation, which only the backend
 * can check.
 */
export type StageAction =
  | { readonly kind: "move"; readonly to: "contacted" | "qualified" }
  | { readonly kind: "won" }
  | { readonly kind: "lost" }
  | { readonly kind: "reopen" };

/** A step the menu shows but cannot take, with where it happens instead. */
export interface StageHint {
  readonly label: string;
  readonly reason: string;
}

export interface StageMenu {
  readonly actions: readonly StageAction[];
  readonly hint: StageHint | null;
}

const QUOTATION_HINT: StageHint = {
  label: "Quoted",
  reason: "Happens when a quotation is sent",
};

const NEGOTIATION_HINT: StageHint = {
  label: "Negotiation",
  reason: "Recorded on the quotation",
};

export function stageMenuFor(stage: LeadStage): StageMenu {
  switch (stage) {
    case "new":
      return { actions: [{ kind: "move", to: "contacted" }, { kind: "lost" }], hint: null };
    case "contacted":
      return { actions: [{ kind: "move", to: "qualified" }, { kind: "lost" }], hint: null };
    case "qualified":
      return { actions: [{ kind: "lost" }], hint: QUOTATION_HINT };
    case "quoted":
      return { actions: [{ kind: "won" }, { kind: "lost" }], hint: NEGOTIATION_HINT };
    case "negotiation":
      return { actions: [{ kind: "won" }, { kind: "lost" }], hint: null };
    case "lost":
      return { actions: [{ kind: "reopen" }], hint: null };
    // won and merged are closed; dormant is set and cleared by the backend's worker.
    case "won":
    case "merged":
    case "dormant":
      return { actions: [], hint: null };
  }
}

/** "Mark as contacted" — the menu's words for each action. */
export function stageActionLabel(action: StageAction): string {
  switch (action.kind) {
    case "move":
      return `Mark as ${LEAD_STAGE_LABELS[action.to].toLowerCase()}`;
    case "won":
      return "Mark as won";
    case "lost":
      return "Mark as lost…";
    case "reopen":
      return "Reopen lead…";
  }
}

const refusalSchema = z.object({
  fields: z.record(z.string(), z.string()).optional(),
});

/**
 * Why the backend refused a stage change, in words the user can act on, and whether the
 * lead on screen is out of date (so the caller shows the latest).
 */
export function stageChangeError(error: unknown): { message: string; stale: boolean } {
  if (!isApiError(error)) {
    return { message: toUserFacingError(error).title, stale: false };
  }

  const fields = refusalSchema.safeParse(error.details).data?.fields ?? {};
  const current = z.enum(LEAD_STAGES).safeParse(fields.stage).data;

  switch (error.code) {
    case "stage_changed":
      return {
        message:
          current === undefined
            ? "Someone moved this lead while you had it open. It now shows the latest."
            : `Someone moved this lead to ${LEAD_STAGE_LABELS[current]} while you had it open. It now shows the latest.`,
        stale: true,
      };
    case "invalid_transition":
    case "stage_terminal":
      return {
        message: "This lead can't move that way any more. It now shows the latest.",
        stale: true,
      };
    case "quotation_required":
      return {
        message:
          fields.to_stage === "won"
            ? "A lead is won when a quotation on it is accepted. Accept the quotation first."
            : "This stage is reached through the lead's quotation.",
        stale: false,
      };
    default:
      return { message: toUserFacingError(error).title, stale: false };
  }
}
