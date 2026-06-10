import { expect, expectCleanConsole, test } from "./fixtures";

test("flyout switches between Comments and Context tabs", async ({
  page,
  problems,
}) => {
  await page.goto("/trading");

  const cards = page.getByTestId("issue-card");
  await cards.first().click();
  await expect(page.getByTestId("issue-flyout")).toBeVisible();

  // All six metadata chips render.
  const chips = page.getByTestId("metadata-chips").locator("> span");
  await expect(chips).toHaveCount(6);

  // Comments tab is selected by default and renders the seeded comments_md.
  await expect(page.getByTestId("tabpanel-comments")).toContainText(
    "Replace with real operator thread",
  );

  // Switching to Context renders the seeded context_md instead.
  await page.getByTestId("tab-context").click();
  await expect(page.getByTestId("tabpanel-context")).toContainText(
    "Synthetic context for",
  );

  // And back to Comments.
  await page.getByTestId("tab-comments").click();
  await expect(page.getByTestId("tabpanel-comments")).toContainText(
    "Operator comments",
  );

  expectCleanConsole(problems);
});
