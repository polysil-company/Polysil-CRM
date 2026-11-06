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
          message: "A colleague or a partner uses this mobile, so it can't be the partner's login.",
        },
        stale: false,
      };
    // FS-071 · the deposit
    case "deposit_pending":
      return {
        refusal: {
          title: "The deposit isn't paid yet",
          message: "Record the deposit, or have it lowered or waived, before approving.",
        },
        stale: false,
      };
    case "deposit_slip_missing":
      return {
        refusal: {
          title: "The deposit's pay slip is missing",
          message: "It was removed from the documents. Record the deposit again with its slip.",
        },
        stale: false,
      };
    case "deposit_not_due":
      return {
        refusal: {
          title: "No deposit is due",
          message: "None is set for this type, or it was waived. The page now shows which.",
        },
        stale: true,
      };
    case "deposit_paid":
      return {
        refusal: {
          title: "The deposit is already paid",
          message: "A paid deposit can't be lowered.",
        },
        stale: true,
      };
    case "deposit_recorded":
      return {
        refusal: {
          title: "A deposit is recorded",
          message: "The type can't change once a deposit is recorded.",
        },
        stale: false,
      };
    case "not_your_relaxation":
      return {
        refusal: {
          title: "You can't lower this deposit",
          message:
            "Only the roles the company settings name lower or waive a deposit, and never whoever started the application.",
        },
        stale: false,
      };
    default: {
      if (error.status === 403) {
        return {
          refusal: {
            title: "You can't decide this one",
            message:
              "Only the roles the company settings name decide an application, and never whoever started it.",
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
