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
});
