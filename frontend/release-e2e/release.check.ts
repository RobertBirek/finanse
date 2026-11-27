import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { expect, test, type APIRequestContext } from "@playwright/test";

async function importStatement(request: APIRequestContext, name: string, mimeType: string) {
  const headers = () => ({ "Idempotency-Key": randomUUID() });
  const created = await request.post("/api/finance/imports", {
    headers: headers(),
    data: { kind: "statement" },
  });
  expect(created.status()).toBe(201);
  const batchId = (await created.json()).id;
  const route = `/api/finance/imports/${batchId}`;
  const uploaded = await request.post(`${route}/sources`, {
    headers: headers(),
    multipart: {
      file: {
        name,
        mimeType,
        buffer: readFileSync(`../backend/tests/test_finance/test_bank_imports/fixtures/${name}`),
      },
    },
  });
  expect(uploaded.status()).toBe(201);
  const id = (await uploaded.json()).source.id;
  const job = await request.post(`${route}/sources/${id}/prepare`, { headers: headers() });
  expect(job.ok()).toBe(true);
  await expect.poll(async () => {
    const result = await request.get(route);
    return (await result.json()).sources.find((item: { id: string }) => item.id === id)
      ?.processing_state;
  }, { timeout: 70_000 }).toBe("ready");
  return batchId;
}

test("installed images serve authenticated ledger and Velo card breakdown", async ({ request, page }) => {
  const email = "release@example.com";
  const password = "OnlyForSyntheticAcceptance1!";
  expect((await request.get("/api/finance/accounts")).status()).toBe(401);
  const user = await request.post("/api/auth/register", {
    headers: { Origin: "http://127.0.0.1:5178" },
    data: { email, password, display_name: "Release check" },
  });
  expect(user.status()).toBe(201);
  await page.goto("/login");
  await page.locator("input[type=email]").fill(email);
  await page.locator("input[type=password]").fill(password);
  const login = page.waitForResponse(r => r.url().endsWith("/api/auth/login"));
  await page.getByRole("button", { name: "Zaloguj się" }).click();
  expect((await login).status()).toBe(204);
  await expect(page).toHaveURL(/\/today$/);
  const response = await page.request.get("/api/finance/accounts");
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual([]);

  const debt = await page.request.post("/api/finance/accounts", {
    data: { name: "Syntetyczny kredyt", type: "credit", currency: "PLN" },
  });
  const payer = await page.request.post("/api/finance/accounts", {
    data: { name: "Syntetyczny rachunek", type: "checking", currency: "PLN" },
  });
  expect(debt.status()).toBe(201);
  expect(payer.status()).toBe(201);
  const loan = await page.request.post("/api/finance/loans", {
    data: {
      name: "Kredyt testowy",
      account_id: (await debt.json()).id,
      payment_account_id: (await payer.json()).id,
    },
  });
  expect(loan.status()).toBe(201);
  const installment = await page.request.post(
    `/api/finance/loans/${(await loan.json()).id}/installments`,
    { data: { number: 1, due_date: "2027-01-15", principal_pln: 90000, interest_pln: 9000, fees_pln: 1000 } },
  );
  expect(installment.status()).toBe(201);
  await page.goto("/finances");
  await page.getByRole("link", { name: "Kredyty i pożyczki" }).click();
  await page.getByRole("button", { name: /Kredyt testowy/ }).click();
  await expect(page.getByRole("heading", { name: "Kredyt testowy" })).toBeVisible();
  const totals = page.locator("dl").filter({ hasText: "Kapitał w harmonogramie" });
  await expect(totals).toContainText("900,00 PLN");
  await expect(totals).toContainText("90,00 PLN");
  await expect(totals).toContainText("10,00 PLN");

  await importStatement(page.request, "revolut_pln.csv", "text/csv");
  const batchId = await importStatement(page.request, "velo_card_komfort.pdf", "application/pdf");
  await page.goto(`/finances/imports/${batchId}`);
  const breakdown = page.getByRole("region", { name: "Co składa się na spłatę karty" });
  await expect(breakdown.getByText("794,39 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText("769,73 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText("24,66 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText(/Rata jest już ujęta/)).toBeVisible();
  await page.goto("/finances/loans");
  await page.getByRole("button", { name: /Plan „Komfort” z wyciągu Velo/ }).first().click();
  const statementPlan = page.getByRole("article").filter({
    hasText: "Plan „Komfort” z wyciągu Velo",
  });
  await expect(statementPlan).toContainText(/12\s000,00 PLN/);
  await expect(statementPlan).toContainText("769,73 PLN");
  await expect(statementPlan.getByRole("link", { name: "Otwórz wyciąg" })).toHaveAttribute(
    "href",
    `/finances/imports/${batchId}`,
  );

  const allegroAccount = await page.request.post("/api/finance/accounts", {
    data: { name: "Allegro testowe", type: "credit", currency: "PLN" },
  });
  expect(allegroAccount.status()).toBe(201);
  const category = await page.request.post("/api/finance/categories", {
    data: { name: "Zakupy testowe", type: "expense" },
  });
  expect(category.status()).toBe(201);
  const accountId = (await allegroAccount.json()).id;
  await page.goto("/settings/finances/loans/allegro-pay");
  const configuration = page.getByRole("form", { name: "Konto i limit" });
  await configuration.getByRole("combobox", { name: "Konto", exact: true }).selectOption(accountId);
  await configuration.getByLabel("Limit PLN").fill("1000");
  await configuration.getByRole("button", { name: "Zapisz konto" }).click();
  const form = page.getByRole("form", { name: "Dodaj zakup" });
  await form.getByLabel("Nazwa").fill("Zakup testowy");
  await form.getByLabel("Data zakupu").fill("2026-01-01");
  await form.getByLabel("Kwota zakupu PLN").fill("200");
  await form.getByRole("combobox", { name: "Wydatek", exact: true }).selectOption("new");
  await form.getByLabel("Kategoria").selectOption((await category.json()).id);
  await form.getByRole("button", { name: "Dodaj ratę" }).click();
  await form.getByLabel("Termin").nth(0).fill("2027-02-01");
  await form.getByLabel("Termin").nth(1).fill("2027-03-01");
  await form.getByLabel("Kapitał PLN").nth(0).fill("100");
  await form.getByLabel("Kapitał PLN").nth(1).fill("100");
  await form.getByRole("button", { name: "Zapisz zakup" }).click();
  await page.getByRole("link", { name: /Otwórz spłaty · Allegro testowe/ }).click();
  await expect(page.getByText("Zakup testowy", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Do pokrycia według harmonogramów/)).toContainText("200,00 PLN");
  const transfer = await page.request.post("/api/finance/transactions", {
    data: {
      description: "Spłata testowa", type: "transfer", transaction_date: "2026-01-15",
      postings: [
        { account_id: (await payer.json()).id, source_amount: 15000, base_amount_pln: 15000, direction: "debit" },
        { account_id: accountId, source_amount: 15000, base_amount_pln: 15000, direction: "credit" },
      ],
    },
  });
  expect(transfer.status()).toBe(201);
  await page.reload();
  const repayments = page.getByRole("form", { name: "Zakupy i spłaty" });
  await repayments.getByLabel("Istniejący przelew").selectOption((await transfer.json()).id);
  await repayments.getByLabel("Przypisz do raty PLN").nth(0).fill("100");
  await repayments.getByLabel("Przypisz do raty PLN").nth(1).fill("50");
  await repayments.getByRole("button", { name: "Przypisz spłatę" }).click();
  await expect(page.getByText(/Do pokrycia według harmonogramów/)).toContainText("50,00 PLN");
});
