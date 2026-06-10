import { expect, expectCleanConsole, test } from "./fixtures";

test("sidebar lists both bindings and navigates on click", async ({
  page,
  problems,
}) => {
  await page.goto("/");

  // Landing pane prompt is visible.
  await expect(page.getByText("Pick a binding from the sidebar")).toBeVisible();

  // Both seeded bindings render as rows.
  const rows = page.getByTestId("binding-row");
  await expect(rows).toHaveCount(2);
  await expect(page.getByRole("link", { name: "homelab" })).toBeVisible();
  await expect(page.getByRole("link", { name: "trading" })).toBeVisible();

  // Clicking a binding navigates to /{binding} and shows the board.
  await page.getByRole("link", { name: "homelab" }).click();
  await expect(page).toHaveURL("/homelab");
  await expect(page.getByRole("heading", { name: "homelab" })).toBeVisible();
  await expect(page.getByTestId("column-todo")).toBeVisible();

  expectCleanConsole(problems);
});
