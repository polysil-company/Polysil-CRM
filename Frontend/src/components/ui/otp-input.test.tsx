import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { OtpInput } from "./otp-input";

function Harness({ onComplete }: { onComplete: (code: string) => void }): React.JSX.Element {
  const [code, setCode] = useState("");
  return (
    <OtpInput aria-label="Code" value={code} onValueChange={setCode} onComplete={onComplete} />
  );
}

describe("[AUTH-001] OtpInput", () => {
  it("keeps digits only, stops at six and completes once", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<Harness onComplete={onComplete} />);
    const input = screen.getByRole("textbox", { name: "Code" });

    await user.click(input);
    await user.paste("48 29-13 7");

    expect(input).toHaveValue("482913");
    expect(onComplete).toHaveBeenCalledExactlyOnceWith("482913");

    await user.keyboard("5");
    expect(input).toHaveValue("482913");
    expect(onComplete).toHaveBeenCalledOnce();
  });

  it("deletes the last digit with backspace", async () => {
    const user = userEvent.setup();
    render(<Harness onComplete={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "Code" });

    await user.type(input, "12{Backspace}");

    expect(input).toHaveValue("1");
  });

  it("offers the platform's SMS code autofill and a numeric keypad", () => {
    render(<Harness onComplete={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "Code" });

    expect(input).toHaveAttribute("autocomplete", "one-time-code");
    expect(input).toHaveAttribute("inputmode", "numeric");
  });
});
