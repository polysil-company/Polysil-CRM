import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Smoke tests: sign-in works, the main routes load against the mocked API, the
 * core journeys work on desktop and phone, and pages pass automated
 * accessibility checks.
 *
 *   npx playwright install chromium   once per machine
 *   npm run test:e2e
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** The mock backend's demo credentials (src/lib/dev/mock-settings.ts). */
const MOCK_STAFF_PASSWORD = "polysil-demo";
const MOCK_OTP_CODE = "123456";

async function expectNoAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(WCAG_TAGS)
    // Development-only overlays: the Next.js dev tools and the TanStack Query devtools.
    .exclude("nextjs-portal")
    .exclude(".tsqd-parent-container")
    .analyze();

  expect(results.violations).toEqual([]);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * The email field by role: `getByLabel("Work email")` also matches the form, whose
 * accessible name is "Sign in with your work email".
 */
function workEmailField(page: Page): Locator {
  return page.getByRole("textbox", { name: "Work email" });
}

/** Signs in as staff and lands on `path`. */
async function signIn(page: Page, path = "/dashboard"): Promise<void> {
  await page.goto(`/sign-in?method=staff&next=${encodeURIComponent(path)}`);
  await workEmailField(page).fill("asha@polysil.in");
  await page.getByLabel("Password", { exact: true }).fill(MOCK_STAFF_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${escapeRegExp(path)}$`));
}

test.describe("[AUTH-006] Signed-in routing", () => {
  test("sends a signed-out visitor to sign-in and back to the page they wanted", async ({
    page,
  }) => {
    await page.goto("/leads");
    await expect(page).toHaveURL(/\/sign-in\?next=%2Fleads$/);

    await page.getByRole("button", { name: "Staff email" }).click();
    await workEmailField(page).fill("asha@polysil.in");
    await page.getByLabel("Password", { exact: true }).fill(MOCK_STAFF_PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(page).toHaveURL(/\/leads$/);
    await expect(page.getByRole("table", { name: "Leads" })).toBeVisible();
  });

  test("keeps the session across a reload, then signs out", async ({ page }) => {
    await signIn(page);
    await page.reload();
    await expect(page.getByRole("region", { name: "Key figures" })).toBeVisible();

    await page.getByRole("button", { name: /Account menu for/ }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();

    await expect(page).toHaveURL(/\/sign-in\?reason=signed-out$/);
    await expect(page.getByText("You've signed out")).toBeVisible();
  });

  test("the sign-in page has no automatically detectable accessibility violations", async ({
    page,
  }) => {
    await page.goto("/sign-in");
    await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[AUTH-001] Mobile sign-in", () => {
  test("signs a channel partner in with a one-time code", async ({ page }) => {
    await page.goto("/sign-in");

    await page.getByLabel("Mobile number").fill("98765 43210");
    await page.getByRole("button", { name: "Send code" }).click();
    await page.getByLabel("6-digit code").fill(MOCK_OTP_CODE);

    await expect(page).toHaveURL(/\/dashboard$/);
  });
});

test.describe("[APP-001] App shell", () => {
  test("sends the root URL to the dashboard once signed in", async ({ page }) => {
    await signIn(page);
    await page.goto("/");

    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test("opens and closes the command menu from the keyboard", async ({ page, isMobile }) => {
    test.skip(isMobile, "Keyboard shortcuts are a desktop feature.");
    await signIn(page);
    await expect(page.getByRole("region", { name: "Key figures" })).toBeVisible();

    await page.keyboard.press("ControlOrMeta+K");
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });
});

test.describe("[RPT-001] Dashboard", () => {
  test("shows the key figures", async ({ page }) => {
    await signIn(page);

    await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    const figures = page.getByRole("region", { name: "Key figures" });
    await expect(figures).toBeVisible();
    await expect(figures.getByText("Open pipeline")).toBeVisible();
  });

  test("has no automatically detectable accessibility violations", async ({ page }) => {
    await signIn(page);
    await expect(page.getByRole("region", { name: "Key figures" })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[LEAD-001] Leads", () => {
  test("opens a lead from the list and comes back", async ({ page }) => {
    await signIn(page, "/leads");
    const table = page.getByRole("table", { name: "Leads" });
    await expect(table).toBeVisible();

    const firstLead = table.getByRole("rowheader").first().getByRole("link");
    const linkText = (await firstLead.textContent()) ?? "";
    await firstLead.click();

    await expect(page).toHaveURL(/\/leads\/[^/?#]+$/);
    const customerName = page.getByRole("main").getByRole("heading", { level: 2 }).first();
    await expect(customerName).toBeVisible();
    expect(linkText).toContain((await customerName.textContent()) ?? "");

    await page.goBack();
    await expect(table).toBeVisible();
  });

  test("restores filters from the URL", async ({ page }) => {
    await signIn(page, "/leads?q=no-such-lead-anywhere");

    await expect(page.getByText("No leads match these filters")).toBeVisible();
  });

  test("has no automatically detectable accessibility violations", async ({ page }) => {
    await signIn(page, "/leads");
    await expect(page.getByRole("table", { name: "Leads" })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[QUOT-012] A customer's quotation link", () => {
  /** A sent quotation in the seeded mock data (src/mocks/data/quotations.ts: mock-{index}). */
  const SHARED_LINK = "/q/mock-3";

  test("opens without signing in and offers the PDF, never opening it by itself", async ({
    page,
  }) => {
    await page.goto(SHARED_LINK);

    await expect(page).toHaveURL(new RegExp(`${escapeRegExp(SHARED_LINK)}$`));
    await expect(page.getByRole("heading", { level: 1 })).toContainText("QT/GJ/");
    await expect(page.getByRole("link", { name: "View quotation" })).toHaveAttribute(
      "target",
      "_blank",
    );
    await expect(page.locator('meta[name="referrer"]')).toHaveAttribute("content", "no-referrer");
  });

  test("has no automatically detectable accessibility violations", async ({ page }) => {
    await page.goto(SHARED_LINK);
    await expect(page.getByRole("link", { name: "View quotation" })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[APPR-001] Approvals", () => {
  test("lists what waits on the manager and asks for a reason to reject", async ({ page }) => {
    await signIn(page, "/approvals");

    const inbox = page.getByRole("list", { name: /Waiting for your decision/ });
    await expect(inbox.getByRole("listitem").first()).toBeVisible();
    await inbox
      .getByRole("listitem")
      .first()
      .getByRole("button", { name: /^Reject/ })
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Reject" }).click();
    await expect(dialog.getByText("Say why. The person who asked reads it.")).toBeVisible();
  });

  test("has no automatically detectable accessibility violations", async ({ page }) => {
    await signIn(page, "/approvals");
    await expect(
      page
        .getByRole("list", { name: /Waiting for your decision/ })
        .getByRole("listitem")
        .first(),
    ).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[SO-001] Sales orders", () => {
  test("lists orders and opens one with its approval chain and dispatches", async ({ page }) => {
    await signIn(page, "/sales-orders?status=partially_dispatched");

    const table = page.getByRole("table", { name: "Sales orders" });
    await expect(table.getByRole("row").nth(1)).toBeVisible();
    await table.getByRole("row").nth(1).getByRole("link").first().click();
    await expect(page.getByRole("list", { name: "Approval steps, in order" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Dispatches, newest first" })).toBeVisible();
  });

  test("has no automatically detectable accessibility violations", async ({ page }) => {
    await signIn(page, "/sales-orders");
    await expect(
      page.getByRole("table", { name: "Sales orders" }).getByRole("row").nth(1),
    ).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[APPR-002] Approval limits", () => {
  test("an administrator sees both ladders and may change a limit", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("polysil:mock-role", "admin");
    });
    await signIn(page, "/approval-limits");

    const orders = page.getByRole("list", { name: "Order value, company-wide" });
    await expect(orders.getByText("Up to ₹1,00,000")).toBeVisible();
    await page
      .getByRole("button", { name: "Change the State Manager limit (Order value, company-wide)" })
      .click();
    await expect(page.getByRole("dialog", { name: "State Manager's order limit" })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[NOTIF-001] Notifications", () => {
  test("the bell lists the latest and opens the quotation one is about", async ({ page }) => {
    await signIn(page, "/dashboard");

    await page.getByRole("button", { name: /^Notifications, \d+ unread$/ }).click();
    const list = page.getByRole("list", { name: "Latest notifications" });
    await list.getByRole("link", { name: /needs your approval/ }).click();
    await expect(page).toHaveURL(/\/quotations\/[^/]+$/);
  });
});

test.describe("[MSG-002] Messages", () => {
  test("opens a conversation and sends a message", async ({ page }) => {
    await signIn(page, "/messages/conv-003");

    const field = page.getByRole("textbox", { name: "Message Sanjay Rao" });
    await field.fill("Order released.");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(
      page.getByRole("log", { name: "Messages" }).getByText("Order released."),
    ).toBeVisible();
  });

  test("keeps a conversation with a colleague who has left readable, and closed", async ({
    page,
  }) => {
    await signIn(page, "/messages/conv-005");

    await expect(page.getByText(/Meera Iyer has left Polysil/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Send message" })).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
  });
});
