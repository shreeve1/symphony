import { expect, expectCleanConsole, test } from "./fixtures";

// Runs against /homelab so the /trading seeds that board.spec asserts on stay
// pristine. Unique title per run: the dev database persists across runs.
test("new issue flow: modal -> Todo card -> survives reload", async ({
  page,
  problems,
}) => {
  const title = `e2e new issue ${Date.now()}`;

  await page.goto("/homelab");
  await page.getByTestId("new-issue-button").click();
  await expect(page.getByTestId("new-issue-modal")).toBeVisible();

  await page.getByTestId("new-issue-title").fill(title);
  // Pick a skill from the seeded catalog (FK-validated server side).
  const skill = page.getByTestId("new-issue-skill");
  await expect(skill.locator("option").nth(1)).toBeAttached();
  await skill.selectOption({ index: 1 });

  const created = page.waitForResponse(
    (res) =>
      res.url().includes("/api/bindings/homelab/issues") &&
      res.request().method() === "POST" &&
      res.status() === 201,
  );
  await page.getByTestId("new-issue-submit").click();

  // Modal closes immediately; the optimistic card lands in the Todo column.
  await expect(page.getByTestId("new-issue-modal")).toBeHidden();
  const todoCard = page
    .getByTestId("column-todo")
    .getByTestId("issue-card")
    .filter({ hasText: title });
  await expect(todoCard).toBeVisible();
  await created;

  // Reload: the card persisted through SQLite.
  await page.reload();
  await expect(todoCard).toBeVisible();

  expectCleanConsole(problems);
});
