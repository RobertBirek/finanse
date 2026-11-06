import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { account, fixtures } from "./fixtures";

for (const theme of ["light", "dark"]) {
  test(`saved account/category colors survive navigation and reload, inherit in charts and can be reset in ${theme}`, async ({
    page,
  }, testInfo) => {
    const mock = await fixtures(page);
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    let accountColor: string | null = null;
    let rootColor: string | null = "#0D9488";
    let childColor: string | null = null;
    const changes: Array<{ entity: string; data: Record<string, unknown> }> =
      [];
    const catalog = () => [
      {
        id: "home",
        name: "Dom",
        type: "expense",
        parent_id: null,
        is_active: true,
        color: rootColor,
      },
      {
        id: "power",
        name: "Prąd",
        type: "expense",
        parent_id: "home",
        is_active: true,
        color: childColor,
      },
    ];
    await page.route("**/api/finance/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      let body: unknown;
      if (url.pathname === "/api/finance/accounts")
        body = [{ ...account, color: accountColor }];
      else if (
        url.pathname === `/api/finance/accounts/${account.id}` &&
        request.method() === "PATCH"
      ) {
        const data = request.postDataJSON();
        changes.push({ entity: "account", data });
        if ("color" in data) accountColor = data.color;
        body = { ...account, color: accountColor };
      } else if (url.pathname === "/api/finance/categories") body = catalog();
      else if (
        url.pathname.startsWith("/api/finance/categories/") &&
        request.method() === "PATCH"
      ) {
        const id = url.pathname.split("/").at(-1)!;
        const data = request.postDataJSON();
        changes.push({ entity: id, data });
        if ("color" in data) {
          if (id === "home") rootColor = data.color;
          else childColor = data.color;
        }
        body = catalog().find((category) => category.id === id);
      } else if (url.pathname === "/api/finance/category-summary") {
        body = {
          month: 11,
          year: 2026,
          groups: [],
          categories: [],
          tree: [
            {
              category_id: "home",
              name: "Dom",
              parent_id: null,
              is_active: true,
              total_pln: 5000,
              direct_total_pln: 2000,
              children: [
                {
                  category_id: "power",
                  name: "Prąd",
                  parent_id: "home",
                  is_active: true,
                  total_pln: 3000,
                  direct_total_pln: 3000,
                  children: [],
                },
              ],
            },
          ],
        };
      } else if (url.pathname === "/api/finance/budget-status") {
        body = {
          month: 11,
          year: 2026,
          items: [
            {
              category_id: "power",
              name: "Prąd",
              parent_id: "home",
              budget_amount_pln: 10000,
              spent_pln: 3000,
              remaining_pln: 7000,
            },
          ],
        };
      } else {
        await route.fallback();
        return;
      }
      await route.fulfill({ json: body });
    });
    await page.goto("/settings/finances/accounts");
    await page.getByRole("button", { name: "Edytuj konto Eurokonto" }).click();
    await page
      .getByRole("button", {
        name: "Kolor konta Eurokonto: Fioletowy",
        exact: true,
      })
      .click();
    await page.getByRole("button", { name: "Zapisz konto Eurokonto" }).click();
    await expect.poll(() => accountColor).toBe("#7C3AED");
    expect(changes[0]).toEqual({
      entity: "account",
      data: { color: "#7C3AED" },
    });
    await page.goto("/finances");
    await expect(page.locator(".finance-bank-mark")).toHaveCSS(
      "background-color",
      "rgb(124, 58, 237)",
    );
    await expect(page.getByLabel("Wykorzystanie budżetu Prąd")).toHaveCSS(
      "accent-color",
      "rgb(13, 148, 136)",
    );
    await page.goto("/settings/finances/categories");
    await page
      .getByRole("button", { name: "Edytuj kategorię Dom", exact: true })
      .click();
    await page
      .getByRole("button", {
        name: "Kolor kategorii Dom: Niebieski",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", { name: "Zapisz kategorię Dom", exact: true })
      .click();
    await expect.poll(() => rootColor).toBe("#2563EB");
    await page.reload();
    await page
      .getByRole("button", { name: "Edytuj kategorię Prąd", exact: true })
      .click();
    await expect(
      page.getByLabel("Kolor kategorii Prąd", { exact: true }),
    ).toHaveValue("#2563eb");
    await page
      .getByRole("button", {
        name: "Kolor kategorii Prąd: Pomarańczowy",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", { name: "Zapisz kategorię Prąd", exact: true })
      .click();
    await expect.poll(() => childColor).toBe("#EA580C");
    await page.goto("/finances/reports");
    await expect(
      page.getByRole("img", { name: "Wydatki: Dom", exact: true }),
    ).toHaveCSS("background-color", "rgb(37, 99, 235)");
    await expect(
      page.getByRole("img", { name: "Wydatki: Prąd", exact: true }),
    ).toHaveCSS("background-color", "rgb(234, 88, 12)");
    await page.screenshot({
      path: testInfo.outputPath("colored-report.png"),
      fullPage: true,
    });
    await page.goto("/settings/finances/categories");
    await page
      .getByRole("button", { name: "Edytuj kategorię Prąd", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Dziedzicz kolor", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Zapisz kategorię Prąd", exact: true })
      .click();
    await expect.poll(() => childColor).toBeNull();
    await page.reload();
    await page
      .getByRole("button", { name: "Edytuj kategorię Prąd", exact: true })
      .click();
    await expect(
      page.getByLabel("Kolor kategorii Prąd", { exact: true }),
    ).toHaveValue("#2563eb");
    await page
      .getByLabel("Kolor kategorii Prąd", { exact: true })
      .scrollIntoViewIfNeeded();
    const accessibility = await new AxeBuilder({ page })
      .include("fieldset")
      .analyze();
    expect(
      accessibility.violations.filter((violation) =>
        ["serious", "critical"].includes(violation.impact ?? ""),
      ),
    ).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath("color-picker.png"),
      fullPage: true,
    });
    expect(changes).toEqual([
      { entity: "account", data: { color: "#7C3AED" } },
      { entity: "home", data: { color: "#2563EB" } },
      { entity: "power", data: { color: "#EA580C" } },
      { entity: "power", data: { color: null } },
    ]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    mock.assertClean();
  });
}
