import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";

/** Why a message was not sent, in words, and what it means for the conversation. */
export interface SendRefusal {
  /** The whole sentence the composer shows. */
  readonly message: string;
  /** The colleague has left: the conversation is read-only from now on. */
  readonly participantLeft: boolean;
}

/**
 * MSG-003 · A failed send, as the composer explains it (backend/docs/api/messages.md):
 * a colleague who has left (`422 participant_inactive`), a lead the sender may not share
 * (`422` on `resource`), or anything else, which is worth a retry.
 */
export function sendRefusal(error: unknown, recipientName: string | null): SendRefusal {
  if (isApiError(error) && error.code === "participant_inactive") {
    return {
      message: `${recipientName ?? "This colleague"} has left Polysil, so new messages can't be sent. Your message stays in the box to copy.`,
      participantLeft: true,
    };
  }
  if (readFieldErrors(error)?.resource !== undefined) {
    return {
      message:
        "This lead can't be shared: it isn't one of the leads you can see. Remove it and send again.",
      participantLeft: false,
    };
  }
  return {
    message: `${toUserFacingError(error).title} Your message is back in the box. Try sending it again.`,
    participantLeft: false,
  };
}
