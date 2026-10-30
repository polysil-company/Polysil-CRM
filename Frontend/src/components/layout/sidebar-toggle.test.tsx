import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SIDEBAR_ATTRIBUTE, SIDEBAR_STORAGE_KEY } from "@/lib/sidebar/sidebar";
import { setSidebarState } from "@/lib/sidebar/sidebar-store";
import { renderWithProviders } from "@/test/render";

import { SidebarToggle } from "./sidebar-toggle";

/** A media query with a fixed answer, to stand in for a desktop or a phone width. */
class FixedMediaQueryList extends EventTarget implements MediaQueryList {
  readonly matches: boolean;
  readonly media: string;
  onchange: ((this: MediaQueryList, event: MediaQueryListEvent) => unknown) | null = null;

  constructor(media: string, matches: boolean) {
    super();
    this.media = media;
    this.matches = matches;
  }

  addListener(): void {
    // Deprecated API — intentionally a no-op in tests.
  }

  removeListener(): void {
    // Deprecated API — intentionally a no-op in tests.
  }
}

describe("[APP-005] SidebarToggle", () => {
  afterEach(() => {
    act(() => {
      setSidebarState("expanded");
    });
    vi.restoreAllMocks();
  });

  it("collapses the sidebar, remembers it, and expands it again", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SidebarToggle />);

    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    const toggle = screen.getByRole("button", { name: "Expand sidebar" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.documentElement).toHaveAttribute(SIDEBAR_ATTRIBUTE, "collapsed");
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("collapsed");

    await user.click(toggle);

    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(document.documentElement).not.toHaveAttribute(SIDEBAR_ATTRIBUTE);
  });

  it("toggles with Ctrl+B on desktop widths only", async () => {
    const user = userEvent.setup();
    const matchMedia = vi
      .spyOn(window, "matchMedia")
      .mockImplementation((query: string) => new FixedMediaQueryList(query, false));
    renderWithProviders(<SidebarToggle />);

    await user.keyboard("{Control>}b{/Control}");
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();

    matchMedia.mockImplementation((query: string) => new FixedMediaQueryList(query, true));
    await user.keyboard("{Control>}b{/Control}");
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });
});
