# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: golden.spec.ts >> customer to analyst to approval
- Location: e2e\golden.spec.ts:4:1

# Error details

```
Test timeout of 90000ms exceeded.
```

```
Error: locator.click: Test timeout of 90000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: /Customer \(Priya\)/ })

```

# Page snapshot

```yaml
- main [ref=e3]:
  - generic [ref=e4]:
    - generic [ref=e5]: Onboarding Copilot
    - paragraph [ref=e8]: Open a bank account in minutes. A human reviewer always makes the final decision.
    - generic [ref=e9]:
      - text: Email
      - textbox "Email" [ref=e10]
    - generic [ref=e11]:
      - text: Password
      - textbox "Password" [ref=e12]
    - button "Sign in" [ref=e13] [cursor=pointer]
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | // Golden path: customer onboards with the bundled clean documents, analyst approves, customer sees the outcome.
  4  | test("customer to analyst to approval", async ({ page, browser }) => {
  5  |   await page.goto("/login");
> 6  |   await page.getByRole("button", { name: /Customer \(Priya\)/ }).click();
     |                                                                  ^ Error: locator.click: Test timeout of 90000ms exceeded.
  7  |   await page.getByRole("button", { name: "Sign in" }).click();
  8  |   await expect(page.getByText("Hi Priya")).toBeVisible();
  9  | 
  10 |   await page.getByRole("button", { name: "Restart demo" }).click();
  11 |   await expect(page.getByText("Hi Priya")).toBeVisible();
  12 | 
  13 |   await page.getByRole("button", { name: "Use a demo document" }).click();
  14 |   await page.locator(".scenario", { hasText: "clean" }).first().getByRole("button", { name: "Upload documents" }).click();
  15 |   await expect(page.getByText("I read your Driving licence")).toBeVisible({ timeout: 60_000 });
  16 | 
  17 |   const composer = page.getByTestId("composer");
  18 |   const reply = async (value: string) => { await composer.fill(value); await composer.press("Enter"); };
  19 |   await reply("9876543210");
  20 |   await reply("priya@example.com");
  21 |   await page.getByRole("button", { name: "Salaried" }).click();
  22 |   await page.getByRole("button", { name: "Skip" }).click();
  23 |   await page.getByRole("button", { name: "No", exact: true }).click();
  24 |   await page.getByRole("button", { name: "Yes", exact: true }).click();
  25 |   await page.getByTestId("submit-btn").click();
  26 |   await expect(page.getByText("Submission #1 is with the reviewer")).toBeVisible();
  27 | 
  28 |   const analyst = await (await browser.newContext()).newPage();
  29 |   await analyst.goto("/login");
  30 |   await analyst.getByRole("button", { name: /Bank analyst/ }).click();
  31 |   await analyst.getByRole("button", { name: "Sign in" }).click();
  32 |   await analyst.getByRole("link", { name: "Review" }).first().click();
  33 |   await expect(analyst.getByText("No inconsistencies")).toBeVisible();
  34 |   await analyst.getByRole("button", { name: "Confirm approve" }).click();
  35 | 
  36 |   await expect(page.getByText(/approved by a bank reviewer/i).first()).toBeVisible({ timeout: 15_000 });
  37 | });
  38 | 
```