import { expect, test } from "@playwright/test";

const ADMIN = { email: "admin@demo.example", password: process.env.E2E_PASSWORD ?? "" };
const STUDENT = { email: "student1@demo.example", password: process.env.E2E_PASSWORD ?? "" };

async function login(page: import("@playwright/test").Page, who: typeof ADMIN) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("institution sees dashboard sections", async ({ page }) => {
  await login(page, ADMIN);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  for (const nav of ["Interviews", "Students", "Knowledge Base"]) await expect(page.getByRole("link", { name: nav })).toBeVisible();
  await expect(page.getByRole("link", { name: "Analytics" })).toHaveCount(0);
  await page.getByRole("link", { name: "Interviews" }).click();
  await expect(page.getByText("AI/ML Engineer Interview (demo)")).toBeVisible();
});

test("student sees only eligible interviews and can open the pre-join check", async ({ page }) => {
  await login(page, STUDENT);
  await page.getByRole("link", { name: "Available Interviews" }).click();
  await expect(page.getByText("AI/ML Engineer Interview (demo)")).toBeVisible();
  await page.getByRole("button", { name: /Join interview|Resume interview/ }).first().click();
  await expect(page.getByText("Before you start")).toBeVisible();
});

test("student cannot open institution pages", async ({ page }) => {
  await login(page, STUDENT);
  await page.goto("/institution/students");
  await expect(page).toHaveURL(/\/student/);
});
