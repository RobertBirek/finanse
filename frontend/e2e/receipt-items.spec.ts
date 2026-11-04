import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures } from "./fixtures";
import {
  categories,
  context,
  hint,
  preview,
} from "../src/components/finance/receipts/receiptTestData";
import type { ReceiptItemsContext, ReceiptBody } from "../src/api/receiptItems";

async function receiptFixture(page: Page, loseApply = false) {
  const base = await fixtures(page),
    unknown: string[] = [],
    writes: {
      action: string;
      body: Record<string, unknown>;
      key: string | undefined;
    }[] = [];
  const empty = (): ReceiptItemsContext => ({
    ...context(0),
    draft: null,
    approved: null,
    calculation: null,
  });
  const states = new Map([
      ["bill", empty()],
      ["second", empty()],
    ]),
    receipts = new Map<string, unknown>();
  let applyCount = 0,
    lost = false;
  const store = {
    id: "store",
    name: "Sklep osiedlowy",
    active: true,
    version: 1,
  };
  const bill = (id: string) => ({
    id,
    kind: "receipt",
    supplier_name: "Zakup w sklepie",
    supplier_tax_id: null,
    number: null,
    issue_date: "2026-11-04",
    sale_date: null,
    due_date: null,
    payee_iban: null,
    description: "Ręczny paragon",
    category_id: null,
    payment_account_id: null,
    total_minor: 9000,
    currency: "PLN",
    declaration: "declared_paid",
    lifecycle: "active",
    review: "approved",
    version: 1,
    paid_minor: 9000,
    remaining_minor: 0,
    reconciliation: "full",
    sources: [],
    allocations: [
      { id: "allocation", posting_id: "account-posting", amount_minor: 9000 },
    ],
    extraction_revision_id: null,
    coverage: null,
    recurring_decision: null,
    forecast_exclusion_reasons: [],
  });
  await page.route("**/api/finance/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname;
    if (path === "/api/finance/categories")
      return route.fulfill({ json: categories });
    if (path === "/api/finance/receipt-stores")
      return route.fulfill({ json: { items: [store], next_cursor: null } });
    if (path === "/api/finance/bills")
      return route.fulfill({
        json: {
          items: [bill("bill"), bill("second")],
          total: 2,
          limit: 25,
          offset: 0,
        },
      });
    const id = path.split("/")[4],
      s = states.get(id);
    if (!s) return route.fallback();
    if (path === `/api/finance/bills/${id}`)
      return route.fulfill({ json: bill(id) });
    const action = path.split("/")[6];
    if (!action && req.method() === "GET")
      return route.fulfill({ json: { ...s, bill_id: id } });
    if (action === "payment")
      return route.fulfill({
        json: { allowed: true, blocked_reason: null, last_application: null },
      });
    if (action === "history")
      return route.fulfill({
        json: {
          items: id === "second" ? [hint] : [],
          match_kind: id === "second" ? "exact" : "none",
          conflict: id === "second",
          has_more: false,
          history_incomplete: false,
        },
      });
    const data = req.postDataJSON() as Record<string, unknown>,
      key = req.headers()["idempotency-key"];
    writes.push({ action, body: data, key });
    if (action === "payment-preview")
      return route.fulfill({
        json: {
          ...preview,
          expected_state_version: s.state_version,
          approved_revision_id: s.approved!.id,
        },
      });
    if (!key) {
      unknown.push(action);
      return route.fulfill({ status: 422, json: { detail: "key required" } });
    }
    if (receipts.has(key)) return route.fulfill({ json: receipts.get(key) });
    let response: unknown;
    if (action === "draft") {
      const body = data.body as ReceiptBody;
      expect(data.expected_version).toBe(s.state_version);
      s.state_version++;
      s.draft = {
        ...context().draft!,
        id: `draft-${s.state_version}`,
        sequence: s.state_version,
        body,
      };
      const total =
        body.lines.reduce((sum, l) => sum + (l.amount_minor ?? 0), 0) -
        body.discounts.reduce((sum, d) => sum + (d.amount_minor ?? 0), 0);
      s.calculation = {
        ...context().calculation!,
        net_total_minor: total,
        difference_minor: total - 9000,
        problems:
          total === 9000
            ? []
            : [
                {
                  code: "mismatch",
                  message: "Różnica: suma musi zgadzać się co do grosza.",
                },
              ],
      };
      s.draft.current =
        total === 9000 &&
        !!body.store_id &&
        body.lines.every((l) => !!l.category_id);
      response = { ...s, bill_id: id };
    } else if (action === "approve") {
      expect(data.confirmed).toBe(true);
      expect(s.draft?.current).toBe(true);
      s.state_version++;
      s.approved = {
        ...s.draft!,
        kind: "approved",
        id: `approved-${s.state_version}`,
        sequence: s.state_version,
      };
      s.draft = null;
      response = { ...s, bill_id: id };
    } else if (action === "payment-apply") {
      expect(data).toEqual({
        expected_state_version: s.state_version,
        approved_revision_id: s.approved!.id,
        expected_preview_snapshot: preview.preview_snapshot,
        confirmed: true,
      });
      applyCount++;
      s.state_version++;
      response = {
        receipt_id: key,
        state_version: s.state_version,
        revision_id: s.approved!.id,
      };
    } else {
      unknown.push(action);
      return route.fulfill({ status: 422, json: { detail: "unregistered" } });
    }
    receipts.set(key, structuredClone(response));
    if (action === "payment-apply" && loseApply && !lost) {
      lost = true;
      return route.abort("failed");
    }
    return route.fulfill({ json: response });
  });
  return {
    writes,
    get applyCount() {
      return applyCount;
    },
    assertClean() {
      expect(unknown).toEqual([]);
      base.assertClean();
    },
  };
}
async function enter(page: Page) {
  await page.goto("/finances/documents?bill=bill");
  await page
    .getByRole("button", { name: "Produkty i kategorie", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Sklep", exact: true })
    .selectOption("store");
  await page
    .getByRole("button", { name: "Dodaj produkt", exact: true })
    .click();
  await page.getByLabel("Produkt 1", { exact: true }).fill("Mleko");
  await page.getByLabel("Kwota produktu 1", { exact: true }).fill("80,00");
  await page.getByLabel("Szukaj: Kategoria produktu 1").fill("spo");
  await page
    .getByLabel("Kategoria produktu 1", { exact: true })
    .selectOption("food");
  await page
    .getByRole("button", { name: "Dodaj produkt", exact: true })
    .click();
  await page.getByLabel("Produkt 2", { exact: true }).fill("Płyn");
  await page.getByLabel("Kwota produktu 2", { exact: true }).fill("20,00");
  await page
    .getByLabel("Kategoria produktu 2", { exact: true })
    .selectOption("home");
  await page.getByRole("button", { name: "Dodaj rabat", exact: true }).click();
  await page.getByLabel("Nazwa rabatu 1", { exact: true }).fill("Kupon");
  await page.getByLabel("Kwota rabatu 1", { exact: true }).fill("10,00");
  await page
    .getByLabel("Udział rabatu 1, produkt 1", { exact: true })
    .fill("8,00");
  await page
    .getByLabel("Udział rabatu 1, produkt 2", { exact: true })
    .fill("2,00");
}
test("manual products, rebates, two confirmations and uncertain apply use exactly one existing payment", async ({
  page,
}) => {
  const api = await receiptFixture(page, true);
  await enter(page);
  await page
    .getByRole("button", { name: "Zapisz robocze", exact: true })
    .click();
  await expect(
    page.getByText("Szkic zapisany.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Zatwierdź pozycje", exact: true })
    .click();
  await expect(
    page.getByText(
      "Pozycje zatwierdzone. Podział płatności wymaga osobnego przeglądu.",
    ),
  ).toBeVisible();
  expect(api.applyCount).toBe(0);
  await page
    .getByRole("button", { name: "Sprawdź podział płatności", exact: true })
    .click();
  await expect(
    page.getByText("Spożywka: 72,00 zł", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Dom: 18,00 zł", { exact: true })).toBeVisible();
  const dialog = page.getByRole("dialog", { name: "Produkty i kategorie" });
  expect(
    (await new AxeBuilder({ page }).include("dialog[open]").analyze())
      .violations,
  ).toEqual([]);
  expect(await dialog.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(
    true,
  );
  await page
    .getByRole("button", { name: "Zatwierdź podział", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Ponów tę samą operację", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Produkt 1", { exact: true })).toBeDisabled();
  await page
    .getByRole("button", { name: "Ponów tę samą operację", exact: true })
    .click();
  await expect(
    page.getByText("Podział zatwierdzony. Nie utworzono nowej płatności."),
  ).toBeVisible();
  const applies = api.writes.filter((w) => w.action === "payment-apply");
  expect(applies).toHaveLength(2);
  expect(applies[0]).toEqual(applies[1]);
  expect(api.applyCount).toBe(1);
  await page
    .getByRole("button", { name: "Zamknij produkty", exact: true })
    .click();
  await page.goto("/finances/documents?bill=second");
  await page
    .getByRole("button", { name: "Produkty i kategorie", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Sklep", exact: true })
    .selectOption("store");
  await page
    .getByRole("button", { name: "Dodaj produkt", exact: true })
    .click();
  await page.getByLabel("Produkt 1", { exact: true }).fill("Mleko");
  await page
    .getByRole("button", { name: "Sprawdź historię sklepu", exact: true })
    .click();
  await expect(
    page.getByText("Ten produkt miał różne kategorie. Wybierz świadomie."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Użyj kategorii", exact: true })
    .click();
  await expect(page.getByText(/Wybrano: Spożywka/)).toBeVisible();
  expect(api.applyCount).toBe(1);
  api.assertClean();
});
test("no history retains full live category search, one grosz mismatch blocks approval and referenced product deletion", async ({
  page,
}) => {
  const api = await receiptFixture(page);
  await enter(page);
  await page
    .getByRole("button", { name: "Sprawdź historię sklepu", exact: true })
    .first()
    .click();
  await expect(
    page.getByText(
      "Brak wskazówki w sprawdzonej historii. Wybierz kategorię z pełnej listy.",
    ),
  ).toBeVisible();
  await page.getByLabel("Szukaj: Kategoria produktu 1").fill("zzzz");
  await expect(
    page.getByText("Brak pasujących kategorii", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Szukaj: Kategoria produktu 1").fill("");
  await expect(
    page.getByLabel("Kategoria produktu 1", { exact: true }).locator("option"),
  ).toHaveCount(3);
  await page
    .getByRole("button", { name: "Usuń produkt 1", exact: true })
    .click();
  await expect(
    page.getByText("Najpierw usuń lub przenieś udziały rabatu tego produktu."),
  ).toBeVisible();
  await page.getByLabel("Kwota produktu 1", { exact: true }).fill("79,99");
  await page
    .getByRole("button", { name: "Zapisz robocze", exact: true })
    .click();
  await expect(
    page.getByText("Różnica do paragonu: -0,01 zł", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Zatwierdź pozycje", exact: true }),
  ).toBeDisabled();
  expect(api.applyCount).toBe(0);
  api.assertClean();
});
