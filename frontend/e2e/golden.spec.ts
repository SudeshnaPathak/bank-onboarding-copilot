import { expect, test } from "@playwright/test";

// Golden path: customer onboards with the bundled clean documents, analyst approves, customer sees the outcome.
test("customer to analyst to approval", async ({ page, browser }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Customer \(Priya\)/ }).click();
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Hi Priya")).toBeVisible();

  await page.getByRole("button", { name: "Restart demo" }).click();
  await expect(page.getByText("Hi Priya")).toBeVisible();

  await page.getByRole("button", { name: "Use a demo document" }).click();
  await page.locator(".scenario", { hasText: "clean" }).first().getByRole("button", { name: "Upload documents" }).click();
  await expect(page.getByText("I read your Driving licence")).toBeVisible({ timeout: 60_000 });

  const composer = page.getByTestId("composer");
  const reply = async (value: string) => { await composer.fill(value); await composer.press("Enter"); };
  await reply("9876543210");
  await reply("priya@example.com");
  await page.getByRole("button", { name: "Salaried" }).click();
  await page.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("button", { name: "No", exact: true }).click();
  await page.getByRole("button", { name: "Yes", exact: true }).click();
  await page.getByTestId("submit-btn").click();
  await expect(page.getByText("Submission #1 is with the reviewer")).toBeVisible();

  const analyst = await (await browser.newContext()).newPage();
  await analyst.goto("/login");
  await analyst.getByRole("button", { name: /Bank analyst/ }).click();
  await analyst.getByRole("button", { name: "Sign in" }).click();
  await analyst.getByRole("link", { name: "Review" }).first().click();
  await expect(analyst.getByText("No inconsistencies")).toBeVisible();
  await analyst.getByRole("button", { name: "Confirm approve" }).click();

  await expect(page.getByText(/approved by a bank reviewer/i).first()).toBeVisible({ timeout: 15_000 });
});
