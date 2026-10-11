import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
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
    expect(screen.getByText(/needs your approval$/)).toBeInTheDocument();
  });

  it("polls only the count until the bell opens, then reads the list", async () => {
    const limits: (string | null)[] = [];
    server.use(
      // Notes each request, then falls through to the mock backend's own handler.
      http.get(buildApiUrl("/notifications"), ({ request }) => {
        limits.push(new URL(request.url).searchParams.get("limit"));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<NotificationBell />);

    const bell = await screen.findByRole("button", { name: "Notifications, 3 unread" });
    expect(limits).toEqual(["1"]);

    await user.click(bell);
    await screen.findByRole("list", { name: "Latest notifications" });
    expect(limits).toEqual(["1", "20"]);
  });

  it("opens the quotation or order a notification is about", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationBell />);

    await user.click(await screen.findByRole("button", { name: "Notifications, 3 unread" }));
    const list = await screen.findByRole("list", { name: "Latest notifications" });

    const quotation = mockDb.notifications.find((item) => item.resource?.type === "quotation");
    const order = mockDb.notifications.find((item) => item.resource?.type === "sales_order");
    expect(
      within(list).getByRole("link", { name: new RegExp(quotation?.title ?? "") }),
    ).toHaveAttribute("href", `/quotations/${quotation?.resource?.id ?? ""}`);
    expect(
      within(list).getByRole("link", { name: new RegExp(order?.title ?? "") }),
    ).toHaveAttribute("href", `/sales-orders/${order?.resource?.id ?? ""}`);
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
