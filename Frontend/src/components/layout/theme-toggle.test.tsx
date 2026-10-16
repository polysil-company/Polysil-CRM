import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { THEME_STORAGE_KEY } from "@/lib/theme/theme";

import { ThemeToggle } from "./theme-toggle";

describe("[APP-002] ThemeToggle", () => {
  afterEach(() => {
    document.documentElement.classList.remove("dark");
  });

  it("opens a labelled theme menu and switches to dark", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    const trigger = screen.getByRole("button", { name: "Change theme" });
    await user.click(trigger);

    expect(await screen.findByText("Theme")).toBeInTheDocument();
    // press-scale keys off this attribute to keep the open trigger full size, so the menu doesn't shift.
    expect(trigger).toHaveAttribute("data-popup-open");
    await user.click(screen.getByRole("menuitemradio", { name: "Dark" }));

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
  });
});
