import { isApiError } from "./errors";

export interface UserFacingError {
  readonly title: string;
  readonly description: string;
  /** "LEAD-001 · 3f2a…" when the error came from an API call. */
  readonly reference: string | undefined;
  readonly retryable: boolean;
}

/**
 * Turns any thrown value into copy a user can act on.
 * Never shows raw server messages — they are logged, not displayed.
 */
export function toUserFacingError(error: unknown): UserFacingError {
  if (!isApiError(error)) {
    return {
      title: "Something went wrong",
      description: "An unexpected problem stopped this from loading. Try again.",
      reference: undefined,
      retryable: true,
    };
  }

  const reference = error.reference;

  switch (error.kind) {
    case "network":
      return {
        title: "You appear to be offline",
        description: "Check your internet connection, then try again.",
        reference,
        retryable: true,
      };
    case "timeout":
      return {
        title: "This is taking too long",
        description: "The server did not respond in time. Try again in a moment.",
        reference,
        retryable: true,
      };
    case "contract":
      return {
        title: "We received data we couldn't read",
        description: "Share the reference below with the support team so they can fix it.",
        reference,
        retryable: false,
      };
    case "unknown":
      return {
        title: "Something went wrong",
        description: "An unexpected problem stopped this from working. Try again.",
        reference,
        retryable: true,
      };
    case "http":
      return httpError(error.status, reference);
  }
}

function httpError(status: number | undefined, reference: string): UserFacingError {
  switch (status) {
    case 401:
      return {
        title: "Your session has ended",
        description: "Sign in again to continue.",
        reference,
        retryable: false,
      };
    case 403:
      return {
        title: "You don't have access to this",
        description: "Ask your manager or an admin if you need access.",
        reference,
        retryable: false,
      };
    case 404:
      return {
        title: "Not found",
        description: "It may have been removed, or the link is wrong.",
        reference,
        retryable: false,
      };
    case 409:
      return {
        title: "This was changed by someone else",
        description: "Reload to see the latest version, then try again.",
        reference,
        retryable: true,
      };
    case 422:
      return {
        title: "Some details need attention",
        description: "Check the highlighted fields and try again.",
        reference,
        retryable: false,
      };
    case 429:
      return {
        title: "Too many requests",
        description: "Wait a few seconds, then try again.",
        reference,
        retryable: true,
      };
    default:
      return {
        title: "Something went wrong on our side",
        description: "The server couldn't complete this request. Try again shortly.",
        reference,
        retryable: true,
      };
  }
}
