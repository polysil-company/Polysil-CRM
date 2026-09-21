import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PasswordInput } from "./password-input";

function renderField(): void {
  render(
    <>
      <label htmlFor="password">Password</label>
      <PasswordInput id="password" />
    </>,
  );
}

describe("[AUTH-003] PasswordInput", () => {
  it("shows and hides the password with a toggle button", async () => {
    const user = userEvent.setup();
    renderField();
    const input = screen.getByLabelText("Password", { selector: "input" });
    const toggle = screen.getByRole("button", { name: "Show password" });

    expect(input).toHaveAttribute("type", "password");
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    await user.click(toggle);

    expect(input).toHaveAttribute("type", "text");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("warns while Caps Lock is on", async () => {
    const user = userEvent.setup();
    renderField();
    const input = screen.getByLabelText("Password", { selector: "input" });

    await user.click(input);
    await user.keyboard("{CapsLock}a");

    expect(screen.getByText("Caps Lock is on")).toBeInTheDocument();
    expect(input.getAttribute("aria-describedby")).toContain("password-caps-lock");
  });
});
