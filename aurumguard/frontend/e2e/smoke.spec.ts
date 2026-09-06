import { expect, test } from "@playwright/test";

test("welcome page shows disclosure and links", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AurumGuard" })).toBeVisible();
  await expect(page.getByText(/not investment advice/i)).toBeVisible();
  await expect(page.getByRole("link", { name: /Create account/ })).toBeVisible();
});

test("manifest is served for PWA install", async ({ request }) => {
  const r = await request.get("/manifest.webmanifest");
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.display).toBe("standalone");
});

test("protected page redirects to login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
