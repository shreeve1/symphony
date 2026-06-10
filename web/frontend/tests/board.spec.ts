import { expect, expectCleanConsole, test } from "./fixtures";
import { STATES } from "@/lib/issues";

test("board renders five columns and opens a flyout on card click", async ({
  page,
  problems,
}) => {
  await page.goto("/trading");

  // Five columns in fixed order: Todo, In Review, Running, Blocked, Done.
  for (const state of STATES) {
    await expect(page.getByTestId(`column-${state.key}`)).toBeVisible();
  }

  // At least one issue card is visible (trading is seeded with two).
  const cards = page.getByTestId("issue-card");
  await expect(cards.first()).toBeVisible();

  // Clicking a card opens the flyout.
  await cards.first().click();
  await expect(page.getByTestId("issue-flyout")).toBeVisible();

  // Clicking the backdrop (outside) closes it.
  await page.getByTestId("flyout-backdrop").click({ position: { x: 5, y: 5 } });
  await expect(page.getByTestId("issue-flyout")).toBeHidden();

  // Run history shows runs without any cost element.
  await cards.first().click();
  await expect(page.getByTestId("run-row").first()).toBeVisible();
  await expect(page.getByTestId("run-cost")).toHaveCount(0);

  expectCleanConsole(problems);
});
