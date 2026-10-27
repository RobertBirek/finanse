import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { account, fixtures } from "./fixtures";

test("selected month survives reload, drilldown Back and finance tabs", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.route("**/api/finance/category-summary?*", (route) => {
    const query = new URL(route.request().url()).searchParams;
    return route.fulfill({
      json: {
        month: Number(query.get("month")),
        year: Number(query.get("year")),
        groups: [],
        categories: [],
        tree: [
          {
            category_id: "home",
            name: "Dom",
            parent_id: null,
            is_active: true,
            direct_total_pln: 10000,
            total_pln: 10000,
            children: [],
          },
        ],
      },
    });
  });
  await page.goto("/finances/reports?month=9&year=2026");
  const picker = page
    .getByRole("button", { name: "Poprzedni miesiąc" })
    .locator("..");
  await expect(picker).toContainText(/wrzesień 2026/i);
  await page.getByRole("button", { name: "Poprzedni miesiąc" }).click();
  await expect(picker).toContainText(/sierpień 2026/i);
  await page.reload();
  await expect(picker).toContainText(/sierpień 2026/i);
  await page.getByRole("link", { name: "Dom", exact: true }).click();
  await expect(page).toHaveURL(/date_from=2026-08-01/);
  await page.goBack();
  await expect(picker).toContainText(/sierpień 2026/i);
  for (const label of ["Budżet", "Przegląd", "Raporty"]) {
    await page.getByRole("link", { name: label, exact: true }).click();
    await expect(picker).toContainText(/sierpień 2026/i);
  }
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

for (const theme of ["light", "dark"]) {
  test(`archived account contrast in ${theme} theme`, async ({ page }) => {
    const api = await fixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    await page.route("**/api/finance/accounts", (route) =>
      route.fulfill({
        json: [
          { ...account, balance_source: 12345 },
          {
            ...account,
            id: "archived",
            name: "Archiwalne konto",
            is_active: false,
            balance_source: 0,
            iban: "DE89370400440532013000",
          },
        ],
      }),
    );
    await page.goto("/settings/finances/accounts");
    await expect(
      page.getByText("Archiwalne konto", { exact: true }),
    ).toBeVisible();
    await page.waitForLoadState("networkidle");
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(scan.violations).toEqual([]);
    expect(api.mutations).toEqual([]);
    api.assertClean();
  });
}

for (const mode of ["success", "denied", "unavailable"] as const) {
  test(`IBAN clipboard ${mode} gives accessible feedback without errors`, async ({
    page,
  }) => {
    const api = await fixtures(page);
    await page.addInitScript((value) => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value:
          value === "unavailable"
            ? undefined
            : {
                writeText: () =>
                  value === "denied"
                    ? Promise.reject(
                        new DOMException("Denied", "NotAllowedError"),
                      )
                    : Promise.resolve(),
              },
      });
    }, mode);
    await page.route("**/api/finance/accounts", (route) =>
      route.fulfill({
        json: [
          { ...account, balance_source: 12345, iban: "DE89370400440532013000" },
        ],
      }),
    );
    await page.goto("/settings/finances/accounts");
    await page.getByRole("button", { name: "Kopiuj", exact: true }).click();
    await expect(page.getByRole("status")).toContainText(
      mode === "success" ? /skopiowan/i : /ręczni/i,
    );
    if (mode !== "success") {
      const manual = page.getByRole("textbox", {
        name: "Numer rachunku do ręcznego skopiowania",
      });
      await expect(manual).toHaveValue("DE89370400440532013000");
      await manual.focus();
      expect(
        await manual.evaluate(
          (element: HTMLInputElement) =>
            element.selectionEnd! - element.selectionStart!,
        ),
      ).toBe(22);
    }
    expect(api.mutations).toEqual([]);
    api.assertClean();
  });
}
