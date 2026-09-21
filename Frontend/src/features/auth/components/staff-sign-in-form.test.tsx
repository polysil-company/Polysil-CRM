import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { MOCK_STAFF_PASSWORD } from "@/lib/dev/mock-settings";
import { server } from "@/mocks/node";

import { StaffSignInForm } from "./staff-sign-in-form";

function renderForm() {
  const onSignedIn = vi.fn();
  const user = userEvent.setup();
  render(<StaffSignInForm onSignedIn={onSignedIn} />);
  return {
    onSignedIn,
    user,
    email: screen.getByLabelText("Work email"),
    password: screen.getByLabelText("Password", { selector: "input" }),
    submit: () => user.click(screen.getByRole("button", { name: "Sign in" })),
  };
}

describe("[AUTH-003] StaffSignInForm", () => {
  it("asks for both fields before sending anything", async () => {
    const { submit, onSignedIn } = renderForm();

    await submit();

    expect(await screen.findByText("Enter your work email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("signs in with a work email and password", async () => {
    const { user, email, password, submit, onSignedIn } = renderForm();

    await user.type(email, "  asha@polysil.in ");
    await user.type(password, MOCK_STAFF_PASSWORD);
    await submit();

    await waitFor(() => {
      expect(onSignedIn).toHaveBeenCalledWith(
        expect.objectContaining({ accessToken: expect.any(String), expiresInSeconds: 900 }),
      );
    });
  });

  it("explains a rejected password, clears it and keeps the email", async () => {
    const { user, email, password, submit, onSignedIn } = renderForm();

    await user.type(email, "asha@polysil.in");
    await user.type(password, "wrong-password");
    await submit();

    expect(await screen.findByText("Email or password is incorrect")).toBeInTheDocument();
    expect(password).toHaveValue("");
    expect(password).toHaveFocus();
    expect(email).toHaveValue("asha@polysil.in");
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("says when the account is locked", async () => {
    server.use(
      http.post(buildApiUrl("/auth/login"), () =>
        HttpResponse.json(
          { error: { code: "account_locked", message: "Locked" } },
          { status: 423 },
        ),
      ),
    );
    const { user, email, password, submit } = renderForm();

    await user.type(email, "asha@polysil.in");
    await user.type(password, MOCK_STAFF_PASSWORD);
    await submit();

    expect(await screen.findByText("Too many attempts")).toBeInTheDocument();
  });

  it("shows a copyable reference when something unexpected fails", async () => {
    server.use(
      http.post(buildApiUrl("/auth/login"), () =>
        HttpResponse.json({ error: { code: "internal", message: "Boom" } }, { status: 500 }),
      ),
    );
    const { user, email, password, submit } = renderForm();

    await user.type(email, "asha@polysil.in");
    await user.type(password, MOCK_STAFF_PASSWORD);
    await submit();

    expect(await screen.findByText("Something went wrong on our side")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy reference" })).toBeInTheDocument();
  });
});
