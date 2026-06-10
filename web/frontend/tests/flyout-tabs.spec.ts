import { expect, expectCleanConsole, test } from "./fixtures";

test("flyout switches between Comments and Context tabs", async ({
  page,
  problems,
}) => {
  await page.goto("/trading");

  const cards = page.getByTestId("issue-card");
  await cards.first().click();
  await expect(page.getByTestId("issue-flyout")).toBeVisible();

  // All seven metadata chips render (#013 added effort and base; priority and
  // max s were dropped from the flyout by operator request).
  const chips = page.getByTestId("metadata-chips").locator("> span");
  await expect(chips).toHaveCount(7);

  // Comments tab is selected by default; #013 renders the blob in an editor
  // textarea, so assert on its value rather than rendered text.
  await expect(page.getByTestId("edit-comments_md")).toHaveValue(
    /Replace with real operator thread/,
  );

  // Switching to Context shows the seeded context_md instead.
  await page.getByTestId("tab-context").click();
  await expect(page.getByTestId("edit-context_md")).toHaveValue(
    /Synthetic context for/,
  );

  // And back to Comments.
  await page.getByTestId("tab-comments").click();
  await expect(page.getByTestId("edit-comments_md")).toHaveValue(
    /Operator comments/,
  );

  expectCleanConsole(problems);
});
