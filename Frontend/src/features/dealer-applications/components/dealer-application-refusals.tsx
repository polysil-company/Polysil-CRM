import type * as React from "react";

import { missingLabel } from "@/features/dealer-applications/lib/dealer-application-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

export interface Refusal {
  readonly title: string;
  readonly message: string;
}

/**
 * CHNL-007 · A refusal in words. `stale` means the application moved on (decided, closed):
 * the dialog closes and the page shows where it stands.
 */
export function refusalOf(error: unknown): { refusal: Refusal; stale: boolean } {
  if (!isApiError(error)) {
    const view = toUserFacingError(error);
    return { refusal: { title: view.title, message: view.description }, stale: false };
  }
  switch (error.code) {
    case "application_closed":
      return {
        refusal: {
          title: "This application is closed",
          message: "It was approved, rejected or withdrawn, so it takes no more changes.",
        },
        stale: true,
      };
    case "already_decided":
      return {
        refusal: {
          title: "Someone has already decided it",
          message: "The page now shows the decision.",
        },
        stale: true,
      };
    case "application_incomplete": {
      const missing = Object.keys(readFieldErrors(error) ?? {}).map(missingLabel);
      return {
        refusal: {
          title: "Something is still missing",
          message:
            missing.length === 0
              ? "Fill in the rest of the application first."
              : `Still needed: ${missing.join(", ")}.`,
        },
        stale: false,
      };
    }
    case "code_in_use":
      return {
        refusal: {
          title: "That partner code is taken",
          message: "Choose another code, or leave it empty for the next one.",
        },
        stale: false,
      };
    case "mobile_in_use":
      return {
        refusal: {
          title: "The mobile already signs someone in",
          message: "A colleague or a partner uses this mobile, so it can't be the dealer's login.",
        },
        stale: false,
      };
    default: {
      if (error.status === 403) {
        return {
          refusal: {
            title: "You can't decide this one",
            message:
              "A State Manager or above decides an application, and never whoever started it.",
          },
          stale: false,
        };
      }
      const view = toUserFacingError(error);
      return { refusal: { title: view.title, message: view.description }, stale: false };
    }
  }
}

export function RefusalNote({ refusal }: { refusal: Refusal | null }): React.JSX.Element | null {
  if (refusal === null) return null;
  return (
    <div
      role="alert"
      className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
    >
      <p className="font-medium text-danger">{refusal.title}</p>
      <p className="text-foreground">{refusal.message}</p>
    </div>
  );
}
