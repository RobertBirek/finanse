import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures } from "./fixtures";

async function noOverflow(page: import("@playwright/test").Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const content = page.locator("#main-content");
  expect(
    await content.evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
  ).toBe(true);
}

test("filters, pagination, browser Back and currency details preserve context", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/finances/transactions?q=Kawa&currency=EUR");
  await expect(page.getByText("Wyniki 1–25 z 53")).toBeVisible();
  await expect(page.getByText("−123,45 EUR").first()).toBeVisible();
  await expect(
    page.getByText("Równowartość: 543,21 PLN").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Następna", exact: true }).click();
  await expect(page.getByText("Wyniki 26–50 z 53")).toBeVisible();
  await page
    .getByRole("button", { name: "Szczegóły: Kawa 25", exact: true })
    .click();
  const detail = page.getByRole("dialog", { name: "Szczegóły transakcji" });
  await expect(detail.getByText("123,45 EUR", { exact: true })).toBeVisible();
  await expect(detail.getByText("543,21 PLN", { exact: true })).toBeVisible();
  await expect(detail.getByText("4.4", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(detail).toHaveCount(0);
  await expect(page).toHaveURL(/page=2/);
  await expect(
    page.getByRole("button", { name: "Szczegóły: Kawa 25", exact: true }),
  ).toBeFocused();
  await page.goBack();
  await expect(page.getByText("Wyniki 1–25 z 53")).toBeVisible();
  await page.getByText(/^Filtry szczegółowe/).click();
  await page.getByLabel("Kwota od (PLN)").fill("1,01");
  await page.getByRole("button", { name: "Zastosuj filtry" }).click();
  await expect
    .poll(() => api.searches.at(-1)?.get("min_amount_pln"))
    .toBe("101");
  await expect(page).not.toHaveURL(/page=2/);
  await noOverflow(page);
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("search failures are not empty results, filters remain available", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.route("**/api/finance/transactions/search**", (route) =>
    route.fulfill({ status: 503, json: { detail: "Fixture unavailable" } }),
  );
  await page.goto("/finances/transactions?q=Kawa");
  await expect(
    page.getByRole("alert").filter({ hasText: "Nie udało się wyszukać" }),
  ).toBeVisible({ timeout: 15000 });
  await expect(
    page.getByLabel("Szukaj po opisie, koncie lub kategorii"),
  ).toHaveValue("Kawa");
  await expect(page.getByText(/Brak transakcji spełniających/)).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Wyczyść filtry" }),
  ).toBeVisible();
  api.assertClean();
});

test("Today failure cannot be mistaken for zero PLN or an empty day", async ({
  page,
}) => {
  const api = await fixtures(page, { todayError: true });
  await page.goto("/today");
  await expect(page.getByRole("alert").first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("0,00 PLN", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("Brak zadań na dziś", { exact: true }),
  ).toHaveCount(0);
  api.assertClean();
});

test("mobile drawer contains focus and Escape restores the trigger", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.setViewportSize({ width: 375, height: 850 });
  await page.goto("/settings");
  const trigger = page.getByRole("button", { name: "Otwórz menu aplikacji" });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await trigger.click();
  const menu = page.getByRole("dialog", { name: "Menu aplikacji" });
  for (const name of [
    "Dzisiaj",
    "Finanse",
    "Projekty",
    "Dokumenty",
    "Doradca",
    "Ustawienia",
  ])
    await expect(menu.getByRole("link", { name, exact: true })).toBeVisible();
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    // Native dialogs may yield to browser chrome (activeElement is body),
    // but never to interactive application content behind the modal.
    expect(
      await menu.evaluate(
        (e) =>
          e.contains(document.activeElement) ||
          document.activeElement === document.body,
      ),
    ).toBe(true);
  }
  await page.locator("#main-content").evaluate((e: HTMLElement) => e.focus());
  await expect(page.locator("#main-content")).not.toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(trigger).toBeFocused();
  api.assertClean();
});

test("empty document status retains controls and a way back to all", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/documents");
  await page.getByRole("button", { name: "Błąd", exact: true }).click();
  await expect(
    page.getByText("Brak dokumentów o wybranym statusie."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Gotowe", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pokaż wszystkie dokumenty" }).click();
  await expect(
    page.getByRole("button", { name: "Otwórz dokument: Faktura.pdf" }),
  ).toBeVisible();
  await noOverflow(page);
  api.assertClean();
});

test("AI approval is visible and requires an explicit click", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/advisor");
  const history = page.getByRole("button", { name: "Rozmowy", exact: true });
  if (await history.isVisible()) await history.click();
  await page
    .getByRole("button", { name: "Rozmowa testowa", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Zatwierdź", exact: true }),
  ).toBeVisible();
  expect(api.mutations).toEqual([]);
  await page.getByRole("button", { name: "Zatwierdź", exact: true }).click();
  await expect(page.getByText("Wykonano", { exact: true })).toBeVisible();
  expect(api.mutations).toEqual([
    "POST /api/advisor/tool-executions/e1/confirm",
  ]);
  api.assertClean();
});
