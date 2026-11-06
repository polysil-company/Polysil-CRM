import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./button";

describe("[DS-001] Button", () => {
  it("works as a plain button", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button onClick={onClick}>Save</Button>);

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("while loading is busy, stays focusable, ignores clicks and announces", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Button state="loading" loadingLabel="Saving…" onClick={onClick}>
        Save
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Saving…" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("aria-disabled", "true");

    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Saving…");
  });

  it("names and announces the success state", () => {
    render(
      <Button state="success" successLabel="Saved">
        Save
      </Button>,
    );

    expect(screen.getByRole("button", { name: "Saved" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });

  it("keeps every label rendered so the width never jumps", () => {
    render(
      <Button state="idle" loadingLabel="Saving…" successLabel="Saved">
        Save
      </Button>,
    );

    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByText("Saving…")).toBeInTheDocument();
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });
});
