import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { MOCK_OTP_CODE } from "@/lib/dev/mock-settings";
import { server } from "@/mocks/node";

import { MobileSignIn } from "./mobile-sign-in";

function renderSignIn() {
  const onSignedIn = vi.fn();
  const user = userEvent.setup();
  render(<MobileSignIn onSignedIn={onSignedIn} />);

  const requestCode = async (mobile = "98765 43210"): Promise<HTMLElement> => {
    await user.type(screen.getByLabelText("Mobile number"), mobile);
    await user.click(screen.getByRole("button", { name: "Send code" }));
    return screen.findByLabelText("6-digit code");
  };

  return { onSignedIn, user, requestCode };
}

function challengeResponse(expiresIn: number, resendAfter: number) {
  return () =>
    HttpResponse.json(
      { data: { sent: true, expires_in: expiresIn, resend_after: resendAfter } },
      { status: 202 },
    );
}

describe("[AUTH-001] MobileSignIn", () => {
  it("checks the number before asking for a code", async () => {
    const { user } = renderSignIn();

    await user.type(screen.getByLabelText("Mobile number"), "12345");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    expect(await screen.findByText("Enter a 10-digit Indian mobile number.")).toBeInTheDocument();
    expect(screen.queryByLabelText("6-digit code")).not.toBeInTheDocument();
  });

  it("signs in with the code from the SMS, without claiming the number is registered", async () => {
    const { user, requestCode, onSignedIn } = renderSignIn();

    const codeInput = await requestCode();

    expect(screen.getByText("+91 98765 43210")).toBeInTheDocument();
    expect(
      screen.getByText(/is registered with Polysil, a 6-digit code is on its way/),
    ).toBeInTheDocument();
    // The step moves focus in an effect just after the field appears; wait for it.
    await waitFor(() => {
      expect(codeInput).toHaveFocus();
    });

    await user.type(codeInput, MOCK_OTP_CODE);

    await waitFor(() => {
      expect(onSignedIn).toHaveBeenCalledWith(expect.objectContaining({ expiresInSeconds: 900 }));
    });
  });

  it("clears a wrong code and explains what to do", async () => {
    const { user, requestCode, onSignedIn } = renderSignIn();
    const codeInput = await requestCode();

    await user.type(codeInput, "000000");

    expect(await screen.findByText("That code didn't work")).toBeInTheDocument();
    expect(codeInput).toHaveValue("");
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("keeps the number when going back to change it", async () => {
    const { user, requestCode } = renderSignIn();
    await requestCode();

    await user.click(screen.getByRole("button", { name: "Change number" }));

    const mobile = await screen.findByLabelText("Mobile number");
    expect(mobile).toHaveValue("98765 43210");
    await waitFor(() => {
      expect(mobile).toHaveFocus();
    });
  });

  it("offers a new code once the wait is over", async () => {
    server.use(http.post(buildApiUrl("/auth/otp/request"), challengeResponse(300, 0)));
    const { user, requestCode } = renderSignIn();
    await requestCode();

    await user.click(screen.getByRole("button", { name: "Send a new code" }));

    expect(await screen.findByText("A new code is on its way.")).toBeInTheDocument();
  });

  it("says when the code has expired", async () => {
    server.use(http.post(buildApiUrl("/auth/otp/request"), challengeResponse(1, 300)));
    const { requestCode } = renderSignIn();
    await requestCode();

    expect(
      await screen.findByText("This code has expired. Send a new one to continue.", undefined, {
        timeout: 3000,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verify and sign in" })).toBeDisabled();
  });
});
