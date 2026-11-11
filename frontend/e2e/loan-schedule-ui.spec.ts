import { expect, test } from "@playwright/test";
import { fixtures } from "./fixtures";
import {
  historyVersions,
  scheduleBatch,
  scheduleInstallment,
  scheduleLoan,
  schedulePreview,
  scheduleReceipt,
  scheduleRow,
} from "../src/test/loanScheduleFixtures";
import { rowFixture } from "../src/test/bankImportFixtures";

for (const theme of ["light", "dark"]) {
  test(`schedule review, preserved identity, explicit confirmation and separate history in ${theme}`, async ({
    page,
  }, testInfo) => {
    const base = await fixtures(page);
    const unexpected: string[] = [];
    const writes: { url: string; body: unknown }[] = [];
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    await page.route("https://ui.test.invalid/api/finance/accounts", (route) =>
      route.fulfill({
        json: [
          {
            id: "debt-a",
            name: "Konto długu",
            type: "credit",
            currency: "PLN",
            is_active: true,
          },
          {
            id: "payer-a",
            name: "Konto spłaty",
            type: "checking",
            currency: "PLN",
            is_active: true,
          },
        ],
      }),
    );
    await page.route("https://ui.test.invalid/api/finance/loans**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/schedule-revisions"))
        return route.fulfill({ json: historyVersions });
      if (path.includes("/schedule-revisions/")) {
        const version = historyVersions.find((v) => path.endsWith(v.id));
        return route.fulfill({
          json: {
            ...version,
            installments: [
              {
                installment_id: "installment-a",
                bank_number: version?.kind === "bank_import" ? 1 : null,
                source_row_id: version?.kind === "bank_import" ? "row-a" : null,
                due_date: scheduleRow.due_date,
                principal_pln: 100000,
                interest_pln: 2000,
                fees_pln: 0,
                balance_after_pln: 0,
              },
            ],
          },
        });
      }
      if (path.endsWith("/loans"))
        return route.fulfill({ json: [scheduleLoan] });
      if (path.endsWith("/loan-a"))
        return route.fulfill({
          json: {
            ...scheduleLoan,
            active_schedule_revision_id: "bank-version",
            installments: [scheduleInstallment],
          },
        });
      unexpected.push(path);
      return route.fulfill({
        status: 404,
        json: { detail: "Unexpected synthetic request" },
      });
    });
    await page.route(
      "https://ui.test.invalid/api/finance/imports**",
      (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (request.method() !== "GET")
          writes.push({ url: path, body: request.postDataJSON() });
        if (path.endsWith("/schedule-preview"))
          return route.fulfill({
            json: { ...schedulePreview, bank_effective_date: "2026-11-01" },
          });
        if (path.endsWith("/activate-schedule") || path.includes("/commands/"))
          return route.fulfill({ json: scheduleReceipt });
        if (path.endsWith("/rows"))
          return route.fulfill({
            json: {
              items: [
                rowFixture({
                  kind: "loan_schedule",
                  bank_fields: null,
                  schedule_fields: scheduleRow,
                  decision: null,
                }),
              ],
              total: 1,
              limit: 100,
              offset: 0,
            },
          });
        if (path.endsWith("/imports"))
          return route.fulfill({ json: [scheduleBatch()] });
        if (path.endsWith("/batch-a"))
          return route.fulfill({ json: scheduleBatch() });
        unexpected.push(path);
        return route.fulfill({
          status: 404,
          json: { detail: "Unexpected synthetic request" },
        });
      },
    );
    await page.goto("/finances/imports/batch-a?loan=loan-a");
    await page.waitForLoadState("networkidle");
    await expect(
      page.getByRole("combobox", { name: "Kredyt", exact: true }),
    ).toHaveValue("loan-a");
    await expect(
      page.getByText("Harmonogram nie księguje spłat"),
    ).toBeVisible();
    await page.getByLabel(/Sprawdziłem przypisanie/).check();
    await page
      .getByRole("button", { name: "Przygotuj podgląd harmonogramu" })
      .click();
    const activate = page.getByRole("button", { name: "Aktywuj harmonogram" });
    await expect(activate).toBeDisabled();
    await expect(page.getByText(/Zachowana historia/)).toBeVisible();
    expect(writes.some((w) => w.url.endsWith("/activate-schedule"))).toBe(
      false,
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("region", { name: "Potwierdzenie harmonogramu" })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: testInfo.outputPath(`schedule-review-${theme}.png`),
      fullPage: true,
    });
    await page.getByLabel(/Potwierdzam aktualizację planu/).check();
    await activate.click();
    await expect(
      page.getByRole("heading", { name: "Harmonogram aktywowany" }),
    ).toBeVisible();
    await page
      .getByRole("link", { name: "Otwórz kredyt i historię wersji" })
      .click();
    await expect(page.getByText(/numer bankowy w wersji: 1/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Dodaj ratę" })).toHaveCount(
      0,
    );
    await page
      .getByRole("button", { name: "Historia wersji harmonogramu" })
      .click();
    await expect(
      page.getByRole("link", { name: /Pobierz oryginał wersji/ }),
    ).toHaveAttribute("href", "/api/documents/document-a/original");
    await page
      .getByRole("combobox", { name: "Wersja harmonogramu", exact: true })
      .selectOption("manual-version");
    await expect(
      page.getByText("Baza ręczna — bez bankowego oryginału PDF."),
    ).toBeVisible();
    expect(
      await page.locator(".card").evaluateAll((nodes) =>
        nodes
          .filter((node) => {
            const r = node.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
          })
          .every((node) => {
            const r = node.getBoundingClientRect();
            return r.left >= -1 && r.right <= window.innerWidth + 1;
          }),
      ),
    ).toBe(true);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page
      .getByText("Snapshot rat — nie bieżące saldo")
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: testInfo.outputPath(`schedule-history-${theme}.png`),
      fullPage: true,
    });
    expect(
      writes.filter((w) => w.url.endsWith("/activate-schedule")),
    ).toHaveLength(1);
    expect(unexpected).toEqual([]);
    base.assertClean();
  });
}
