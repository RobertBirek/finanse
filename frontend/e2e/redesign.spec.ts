import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures, account } from "./fixtures";

test("approved finance surfaces remain responsive and real configuration stays in settings", async ({
  page,
}, testInfo) => {
  test.setTimeout(90000);
  const api = await fixtures(page);
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({
      json: [
        {
          ...account,
          balance_source: 12345,
          bank_name: "Bank testowy",
          iban: "DE89370400440532013000",
        },
      ],
    }),
  );
  const categories = [
    {
      id: "root",
      name: "Dom",
      type: "expense",
      parent_id: null,
      is_active: false,
    },
    {
      id: "media",
      name: "Media",
      type: "expense",
      parent_id: "root",
      is_active: true,
    },
    {
      id: "power",
      name: "Prąd",
      type: "expense",
      parent_id: "media",
      is_active: true,
    },
  ];
  await page.route("**/api/finance/categories", (route) =>
    route.fulfill({ json: categories }),
  );
  for (const path of [
    "/finances",
    "/finances/budgets",
    "/finances/cashflow",
    "/finances/reports",
    "/settings",
    "/settings/finances/accounts",
    "/settings/finances/categories",
    "/settings/finances/budgets",
    "/settings/finances/schedules",
    "/settings/finances/forecast",
  ]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("#main-content h1").first()).toBeVisible();
    expect(
      await page
        .locator("#main-content")
        .evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
      path,
    ).toBe(true);
    if (path === "/finances") {
      await expect(page.getByLabel("Łączne saldo kont")).toContainText(
        "543,21",
      );
      await expect(page.getByText("123,45 EUR", { exact: true })).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Dodaj konto", exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("img", { name: "Prognozowany przebieg salda" }),
      ).toBeVisible();
    }
    if (path === "/settings/finances/categories") {
      await expect(page.getByText("Prąd", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Zwiń Dom", exact: true }).click();
      await expect(page.getByText("Prąd", { exact: true })).toHaveCount(0);
      await page
        .getByRole("button", { name: "Rozwiń Dom", exact: true })
        .click();
    }
    if (path === "/settings/finances/accounts") {
      await expect(page.getByText("DE89370400440532013000")).toHaveCount(0);
      await page.getByRole("button", { name: "Pokaż", exact: true }).click();
      await expect(page.getByText("DE89370400440532013000")).toBeVisible();
    }
    if (
      [
        "/finances",
        "/settings/finances/categories",
        "/settings/finances/accounts",
      ].includes(path)
    ) {
      await page.screenshot({
        path: `/tmp/opencode/finance-ui-${testInfo.project.name}-${path.replaceAll("/", "-")}.png`,
        fullPage: true,
      });
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect(scan.violations).toEqual([]);
    }
  }
  await page.goto("/finances");
  await page.getByRole("button", { name: "Włącz ciemny motyw" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.screenshot({
    path: `/tmp/opencode/finance-ui-${testInfo.project.name}-dark.png`,
    fullPage: true,
  });
  expect(api.mutations).toEqual([]);
  if (testInfo.project.name === "desktop") {
    for (const width of [320, 768]) {
      await page.setViewportSize({ width, height: 900 });
      for (const path of [
        "/finances",
        "/finances/transactions",
        "/settings/finances/categories",
        "/settings/finances/accounts",
        "/settings/finances/forecast",
      ]) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        expect(
          await page
            .locator("#main-content")
            .evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
          `${width}: ${path}`,
        ).toBe(true);
      }
    }
  }
  api.assertClean();
});
