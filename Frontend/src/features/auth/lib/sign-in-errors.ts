import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";

export interface SignInErrorView {
  readonly title: string;
  readonly description: string;
  /** Only for unexpected failures, where support needs to find the request. */
  readonly reference: string | undefined;
}

/**
 * Copy for everything that can stop a sign-in. The backend deliberately gives one
 * answer for a wrong password, an unknown address and a disabled account, and one
 * for a wrong, expired or used-up code — the copy must not guess which it was.
 */
export function describeSignInError(error: unknown): SignInErrorView {
  if (isApiError(error) && error.kind === "http") {
    switch (error.code) {
      case "invalid_credentials":
        return {
          title: "Email or password is incorrect",
          description: "Check both and try again. Passwords are case-sensitive.",
          reference: undefined,
        };
      case "account_locked":
        return {
          title: "Too many attempts",
          description:
            "Sign-in is paused for this account for 15 minutes. Try again later, or ask your administrator for help.",
          reference: undefined,
        };
      case "invalid_otp":
        return {
          title: "That code didn't work",
          description: "It may be mistyped or expired. Try again, or send a new code.",
          reference: undefined,
        };
      default:
        break;
    }
  }

  const view = toUserFacingError(error);
  return { title: view.title, description: view.description, reference: view.reference };
}
