import { expect, test } from "@playwright/test";
import { fixtures, account } from "./fixtures";
import { financialDocumentFixtures, ids } from "./financial-document-fixtures";
import { categorySelectFixture } from "../src/test/categoryFixtures";

const expenseLabels = ["Auto - Zamek", "Dom - Gaz", "Dom - Woda"];

test("transaction form and historical filter share full sorted paths without changing IDs", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.route("**/api/finance/categories", (route) =>
    route.fulfill({ json: categorySelectFixture }),
  );
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({ json: [{ ...account, currency: "PLN" }] }),
  );
  await page.goto("/finances/transactions?create=expense");
  const dialog = page.getByRole("dialog", { name: "Dodaj transakcję" });
  const category = dialog.getByLabel("Kategoria", { exact: true });
  await expect(category.locator("option")).toHaveText([
    "Wybierz kategorię",
    ...expenseLabels,
  ]);
  await category.selectOption("gas");
  await expect(category).toHaveValue("gas");
  await expect(category.locator("option:checked")).toHaveText("Dom - Gaz");
  await dialog.getByLabel("Szukaj: Kategoria").fill("Dom - Woda");
  await expect(category.locator("option")).toHaveText([
    "Wybierz kategorię",
    "Dom - Gaz",
    "Dom - Woda",
  ]);
  await page.screenshot({
    path: test.info().outputPath("transaction-path.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await dialog.getByRole("button", { name: "Zamknij formularz" }).click();
  await page.getByText(/Filtry szczegółowe/).click();
  const filter = page.getByRole("combobox", { name: "Kategoria", exact: true });
  await expect(filter.locator("option")).toHaveText([
    "Wszystkie kategorie",
    "Auto (archiwalna)",
    "Auto - Zamek",
    "Dom (archiwalna)",
    "Dom - Gaz",
    "Dom - Stara (archiwalna)",
    "Dom - Woda",
    "Pensja",
  ]);
  await filter.selectOption("water");
  await page.getByRole("button", { name: "Zastosuj filtry" }).click();
  await expect(page).toHaveURL(/category_id=water/);
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("category parent selectors keep complete paths and cycle exclusions", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.route("**/api/finance/categories", (route) =>
    route.fulfill({ json: categorySelectFixture }),
  );
  await page.goto("/settings/finances/categories");
  const create = page.getByRole("form", { name: "Nowa kategoria" });
  await expect(
    create.getByLabel("Kategoria nadrzędna").locator("option"),
  ).toHaveText([
    "brak",
    "Auto",
    "Auto - Zamek",
    "Dom",
    "Dom - Gaz",
    "Dom - Stara",
    "Dom - Woda",
    "Pensja",
  ]);
  await page
    .getByRole("button", { name: "Edytuj kategorię Dom", exact: true })
    .click();
  const edit = page.getByLabel("Kategoria nadrzędna").first();
  await expect(edit.locator("option")).toHaveText([
    "Brak rodzica",
    "Auto (archiwalna)",
    "Auto - Zamek",
  ]);
  await edit.selectOption("auto-child");
  await expect(edit).toHaveValue("auto-child");
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("bill payment and document review use the same full active expense labels", async ({
  page,
}) => {
  const api = await financialDocumentFixtures(page);
  await page.route("**/api/finance/categories", (route) =>
    route.fulfill({ json: categorySelectFixture }),
  );
  await page.goto(`/finances/documents?bill=${ids.bill}`);
  await page
    .getByRole("button", { name: "Powiąż płatność", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Zarejestruj płatność", exact: true })
    .click();
  await expect(
    dialog.getByLabel("Kategoria", { exact: true }).locator("option"),
  ).toHaveText(["Wybierz kategorię", ...expenseLabels]);
  await dialog.getByLabel("Kategoria", { exact: true }).selectOption("water");
  await expect(dialog.getByLabel("Kategoria", { exact: true })).toHaveValue(
    "water",
  );
  await dialog.getByRole("button", { name: "Anuluj", exact: true }).click();
  await page.goto("/documents");
  await page
    .getByRole("button", { name: "Otwórz dokument: stara-faktura.pdf" })
    .click();
  await page.getByRole("button", { name: "Sprawdź dane", exact: true }).click();
  await expect(
    page.getByLabel("Kategoria", { exact: true }).locator("option"),
  ).toHaveText(["Nie wybieraj teraz", ...expenseLabels]);
  expect(api.mutations).toEqual([]);
  api.assertClean();
});
