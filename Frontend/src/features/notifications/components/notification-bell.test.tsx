import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { resetMockDb } from "@/mocks/db";
import { renderWithProviders } from "@/test/render";

import { NotificationBell } from "./notification-bell";

describe("[NOTIF-001] NotificationBell", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("says how many are unread and lists the latest notifications", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: "Notifications, 3 unread" }));

    expect(await screen.findByRole("list", { name: "Latest notifications" })).toBeInTheDocument();
    expect(screen.getByText("Quotation QT-26-00412 needs your approval")).toBeInTheDocument();
  });

  it("marks everything as read (NOTIF-002)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: "Notifications, 3 unread" }));
    await user.click(await screen.findByRole("button", { name: "Mark all as read" }));

    expect(await screen.findByRole("button", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark all as read" })).toBeDisabled();
  });
});
