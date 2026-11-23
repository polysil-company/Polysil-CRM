import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { acceptSessionTokens, endSession, getAuthSnapshot } from "@/lib/auth/session-store";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { ChangePasswordForm } from "./change-password-form";
import { SignInScreen } from "./sign-in-screen";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const NEW_PASSWORD = "monsoon drip lines";

interface Sent {
  body: unknown;
  key: string | null;
}

/** POST /auth/password answering as given; records what was sent. */
function answerChange(response: () => Response): Sent[] {
  const sent: Sent[] = [];
  server.use(
    http.post(buildApiUrl("/auth/password"), async ({ request }) => {
      sent.push({ body: await request.json(), key: request.headers.get("idempotency-key") });
      return response();
    }),
  );
  return sent;
}

async function fill(
  user: ReturnType<typeof userEvent.setup>,
  { current, next, again }: { current: string; next: string; again: string },
): Promise<void> {
  await user.type(screen.getByLabelText("Current password"), current);
  await user.type(screen.getByLabelText("New password"), next);
  await user.type(screen.getByLabelText("New password, again"), again);
  await user.click(screen.getByRole("button", { name: "Change password" }));
}

function show(): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  acceptSessionTokens({ accessToken: "mock.0.test", expiresInSeconds: 900 });
  renderWithProviders(<ChangePasswordForm />);
  return user;
}

describe("[AUTH-007] ChangePasswordForm", () => {
  afterEach(() => {
    endSession("signed-out", { fromOtherTab: true });
  });

  it("checks the three fields before sending anything", async () => {
    const sent = answerChange(() => new HttpResponse(null, { status: 204 }));
    const user = show();

    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(screen.getByText("Enter your current password.")).toBeInTheDocument();
    expect(screen.getByText("Choose a new password.")).toBeInTheDocument();
    expect(screen.getByText("Type the new password again.")).toBeInTheDocument();

    await fill(user, { current: "temporary-pass", next: "short", again: "shorter" });
    expect(screen.getByText("At least 12 characters.")).toBeInTheDocument();
    expect(screen.getByText("The two new passwords don't match.")).toBeInTheDocument();
    expect(sent).toHaveLength(0);
  });

  it("says when the current password is wrong, and keeps the new one", async () => {
    answerChange(() =>
      HttpResponse.json(
        {
          error: {
            code: "validation_error",
            message: "Request validation failed.",
            fields: { current_password: "wrong" },
          },
        },
        { status: 422 },
      ),
    );
    const user = show();

    await fill(user, { current: "not-it", next: NEW_PASSWORD, again: NEW_PASSWORD });

    expect(await screen.findByText("That isn't your current password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue(NEW_PASSWORD);
    expect(getAuthSnapshot().status).toBe("signed-in");
  });

  it("sends both passwords with a key, then ends the session to sign in again", async () => {
    const sent = answerChange(() => new HttpResponse(null, { status: 204 }));
    const user = show();

    await fill(user, { current: "temporary-pass", next: NEW_PASSWORD, again: NEW_PASSWORD });

    await vi.waitFor(() => {
      expect(getAuthSnapshot()).toMatchObject({
        status: "signed-out",
        endReason: "password-changed",
      });
    });
    expect(sent).toHaveLength(1);
    expect(sent[0]?.body).toEqual({
      current_password: "temporary-pass",
      new_password: NEW_PASSWORD,
    });
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("signs out to use the administrator's password when it was reset meanwhile", async () => {
    answerChange(() =>
      HttpResponse.json(
        {
          error: {
            code: "password_changed_meanwhile",
            message: "An administrator reset the password.",
          },
        },
        { status: 409 },
      ),
    );
    const user = show();

    await fill(user, { current: "temporary-pass", next: NEW_PASSWORD, again: NEW_PASSWORD });

    await vi.waitFor(() => {
      expect(getAuthSnapshot().endReason).toBe("password-reset");
    });
  });
});

describe("[AUTH-007] SignInScreen after a password change", () => {
  it("says to use the new password and opens the email form", () => {
    renderWithProviders(<SignInScreen next={null} reason="password-changed" />);

    expect(screen.getByText("Password changed")).toBeInTheDocument();
    expect(screen.getByLabelText("Work email")).toBeInTheDocument();
  });

  it("says to use the administrator's password after a reset", () => {
    renderWithProviders(<SignInScreen next={null} reason="password-reset" />);

    expect(screen.getByText("Your administrator set a new password")).toBeInTheDocument();
  });
});
