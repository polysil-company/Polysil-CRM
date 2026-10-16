import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { sendRefusal } from "./send-refusal";

function refusal(code: string, fields?: Record<string, string>): ApiError {
  return new ApiError({
    kind: "http",
    message: "Refused",
    dataId: "MSG-003",
    requestId: "req-1",
    method: "POST",
    path: "/conversations/c-1/messages",
    status: 422,
    code,
    details: fields === undefined ? undefined : { fields },
  });
}

describe("[MSG-003] sendRefusal", () => {
  it("says the colleague has left, and that the conversation is closed", () => {
    expect(sendRefusal(refusal("participant_inactive"), "Meera Iyer")).toEqual({
      message:
        "Meera Iyer has left Polysil, so new messages can't be sent. Your message stays in the box to copy.",
      participantLeft: true,
    });
  });

  it("explains a lead that can't be shared", () => {
    const view = sendRefusal(
      refusal("validation_error", { resource: "not a lead you can see" }),
      "Priya Nair",
    );

    expect(view.message).toMatch(/^This lead can't be shared/);
    expect(view.participantLeft).toBe(false);
  });

  it("asks for a retry on anything else", () => {
    expect(sendRefusal(new Error("offline"), null).message).toMatch(/Try sending it again\.$/);
  });
});
