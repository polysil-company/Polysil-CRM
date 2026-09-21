import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Smoke tests: the main routes load against the mocked API, the core journeys
 * work on desktop and phone, and pages pass automated accessibility checks.
 *
 *   npx playwright install chromium   once per machine
 *   npm run test:e2e
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectNoAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(WCAG_TAGS)
    // Development-only overlays: the Next.js dev tools and the TanStack Query devtools.
    .exclude("nextjs-portal")
    .exclude(".tsqd-parent-container")
    .analyze();

  expect(results.violations).toEqual([]);
}

test.describe("[APP-001] App shell", () => {
  test("sends the root URL to the dashboard", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test("opens and closes the command menu from the keyboard", async ({ page, isMobile }) => {
    test.skip(isMobile, "Keyboard shortcuts are a desktop feature.");
    await page.goto("/dashboard");
    await expect(page.getByRole("region", { name: "Key figures" })).toBeVisible();

    await page.keyboard.press("ControlOrMeta+K");
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });
});

test.describe("[RPT-001] Dashboard", () => {
  test("shows the key figures", async ({ page }) => {
    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    const figures = page.getByRole("region", { name: "Key figures" });
    await expect(figures).toBeVisible();
    await expect(figures.getByText("Open pipeline")).toBeVisible();
  });

  test("has no automatically detectable accessibility violations", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByRole("region", { name: "Key figures" })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});

test.describe("[LEAD-001] Leads", () => {
  test("opens a lead from the list and comes back", async ({ page }) => {
    await page.goto("/leads");
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
    await page.goto("/leads?q=no-such-lead-anywhere");

    await expect(page.getByText("No leads match these filters")).toBeVisible();
  });

  test("has no automatically detectable accessibility violations", async ({ page }) => {
    await page.goto("/leads");
    await expect(page.getByRole("table", { name: "Leads" })).toBeVisible();

    await expectNoAccessibilityViolations(page);
  });
});
