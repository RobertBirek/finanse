import { expect, test } from "@playwright/test";
import { fixtures } from "./fixtures";
import {
  scheduleBatch,
  scheduleLoan,
  schedulePreview,
  scheduleReceipt,
  scheduleRow,
} from "../src/test/loanScheduleFixtures";
import { rowFixture } from "../src/test/bankImportFixtures";

for (const lostReply of [false, true]) {
  test(`schedule upload remains a plan, duplicate stays in original batch, receipt survives reload${lostReply ? " after lost response" : ""}`, async ({
    page,
  }) => {
    const base = await fixtures(page);
    let uploaded = false;
    let committed = false;
    let sends = 0;
    const unexpected: string[] = [];
    const keys: string[] = [];
    const mutations: string[] = [];
    await page.route("https://ui.test.invalid/api/finance/loans", (route) =>
      route.fulfill({ json: [scheduleLoan] }),
    );
    await page.route(
      "https://ui.test.invalid/api/finance/loans/loan-a",
      (route) => route.fulfill({ json: { ...scheduleLoan, installments: [] } }),
    );
    await page.route("https://ui.test.invalid/api/finance/accounts", (route) =>
      route.fulfill({
        json: [
          {
            id: "debt-a",
            name: "Dług",
            currency: "PLN",
            type: "credit",
            is_active: true,
          },
          {
            id: "payer-a",
            name: "Płatnik",
            currency: "PLN",
            type: "checking",
            is_active: true,
          },
        ],
      }),
    );
    await page.route(
      "https://ui.test.invalid/api/finance/imports**",
      async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        const method = request.method();
        if (method !== "GET") mutations.push(path);
        const batch = {
          ...scheduleBatch(),
          sources: uploaded
            ? scheduleBatch().sources.map((s) => ({
                ...s,
                schedule_activations: committed
                  ? [
                      {
                        source_revision_id: "revision-a",
                        result: scheduleReceipt,
                      },
                    ]
                  : [],
              }))
            : [],
          commit_state: committed ? "committed" : "not_committed",
          unresolved_count: committed ? 0 : 1,
        };
        if (path.endsWith("/imports") && method === "POST") {
          expect(request.postDataJSON()).toEqual({ kind: "loan_schedule" });
          return route.fulfill({ status: 201, json: batch });
        }
        if (path.endsWith("/imports")) return route.fulfill({ json: [batch] });
        if (path.endsWith("/sources")) {
          const duplicate = uploaded;
          uploaded = true;
          return route.fulfill({
            status: 201,
            json: {
              source: scheduleBatch().sources[0],
              is_duplicate: duplicate,
              existing_batch_id: duplicate ? "batch-a" : null,
            },
          });
        }
        if (path.endsWith("/prepare"))
          return route.fulfill({
            json: {
              id: "durable-job",
              source_id: "source-a",
              state: "queued",
              attempts: 0,
              error_code: null,
              revision_id: null,
            },
          });
        if (path.endsWith("/batch-a")) return route.fulfill({ json: batch });
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
              offset: 0,
              limit: 100,
            },
          });
        if (path.endsWith("/schedule-preview"))
          return route.fulfill({ json: schedulePreview });
        if (path.endsWith("/activate-schedule")) {
          sends++;
          keys.push(request.headers()["idempotency-key"]);
          expect(Object.keys(request.postDataJSON()).sort()).toEqual([
            "preview_id",
            "request_hash",
          ]);
          committed = true;
          if (lostReply) return route.abort("failed");
          return route.fulfill({ json: scheduleReceipt });
        }
        if (path.includes("/commands/"))
          return committed
            ? route.fulfill({ json: scheduleReceipt })
            : route.fulfill({ status: 404, json: { detail: "No result" } });
        unexpected.push(path);
        return route.fulfill({
          status: 404,
          json: { detail: "Unexpected synthetic request" },
        });
      },
    );
    await page.goto("/finances/imports?kind=loan_schedule&loan=loan-a");
    const file = {
      name: "synthetic-schedule.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from(
        "Synthetic UI-only PDF upload; real PDF parser exercised in PostgreSQL acceptance",
      ),
    };
    await page.getByLabel("Pliki harmonogramów").setInputFiles(file);
    await page.getByRole("button", { name: "Dodaj pliki" }).click();
    await expect(
      page.getByRole("link", { name: "Sprawdź import" }),
    ).toBeVisible();
    expect(sends).toBe(0);
    expect(mutations.some((p) => p.endsWith("/schedule-preview"))).toBe(false);
    await page.getByLabel("Pliki harmonogramów").setInputFiles(file);
    await page.getByRole("button", { name: "Dodaj pliki" }).click();
    await expect(page.getByText(/To źródło już istnieje/)).toBeVisible();
    await page.getByRole("link", { name: "Otwórz istniejący import" }).click();
    await expect(
      page.getByRole("combobox", { name: "Kredyt", exact: true }),
    ).toHaveValue("loan-a");
    await page.getByLabel(/Sprawdziłem przypisanie/).check();
    await page
      .getByRole("button", { name: "Przygotuj podgląd harmonogramu" })
      .click();
    await expect(
      page.getByRole("button", { name: "Aktywuj harmonogram" }),
    ).toBeDisabled();
    await page.getByLabel(/Potwierdzam aktualizację planu/).check();
    await page.getByRole("button", { name: "Aktywuj harmonogram" }).click();
    await expect(
      page.getByRole("heading", { name: "Harmonogram aktywowany" }),
    ).toBeVisible();
    expect(sends).toBe(1);
    expect(keys[0]).toBeTruthy();
    await page.goto("/finances/imports?kind=loan_schedule");
    await page.reload();
    await expect(page.getByText("Zatwierdzony", { exact: true })).toBeVisible();
    await page.getByRole("link", { name: "schedule.pdf", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Harmonogram aktywowany" }),
    ).toBeVisible();
    await expect(
      page.getByText(/Potwierdzenie: schedule-receipt/),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
    ).toHaveCount(0);
    expect(sends).toBe(1);
    expect(
      mutations.some((p) => p.endsWith("/commit") || p.includes("/payments")),
    ).toBe(false);
    expect(unexpected).toEqual([]);
    base.assertClean();
  });
}

for (const theme of ["light", "dark"]) {
  test(`explicit reparse comparison identifies the original receipt without a second plan in ${theme}`, async ({
    page,
  }, testInfo) => {
    const base = await fixtures(page);
    const unexpected: string[] = [];
    let activations = 0;
    await page.addInitScript(
      (value) => localStorage.setItem("advisor-theme", value),
      theme,
    );
    await page.route("https://ui.test.invalid/api/finance/accounts", (route) =>
      route.fulfill({
        json: [
          {
            id: "debt-a",
            name: "Dług",
            type: "credit",
            currency: "PLN",
            is_active: true,
          },
          {
            id: "payer-a",
            name: "Płatnik",
            type: "checking",
            currency: "PLN",
            is_active: true,
          },
        ],
      }),
    );
    await page.route("https://ui.test.invalid/api/finance/loans", (route) =>
      route.fulfill({ json: [scheduleLoan] }),
    );
    await page.route(
      "https://ui.test.invalid/api/finance/loans/loan-a",
      (route) => route.fulfill({ json: { ...scheduleLoan, installments: [] } }),
    );
    await page.route(
      "https://ui.test.invalid/api/finance/imports**",
      (route) => {
        const req = route.request();
        const path = new URL(req.url()).pathname;
        if (path.endsWith("/batch-a")) {
          const batch = scheduleBatch();
          return route.fulfill({
            json: {
              ...batch,
              commit_state: "committed",
              unresolved_count: 0,
              sources: batch.sources.map((s) => ({
                ...s,
                candidate_revision_id: "revision-new",
                candidate_parser_version: "v2",
                candidate_checks: s.checks,
                schedule_activations: [
                  { source_revision_id: "revision-a", result: scheduleReceipt },
                ],
              })),
            },
          });
        }
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
              limit: 1000,
              offset: 0,
            },
          });
        if (path.endsWith("/schedule-preview")) {
          const data = req.postDataJSON();
          expect(data.source_revision_id).toBe("revision-new");
          expect(data.acknowledgements).toContain(
            "reparse_comparison:source-a:revision-new",
          );
          return route.fulfill({
            json: {
              ...schedulePreview,
              source_revision_id: "revision-new",
              existing_activation: scheduleReceipt,
            },
          });
        }
        if (path.endsWith("/activate-schedule")) activations++;
        unexpected.push(path);
        return route.fulfill({
          status: 404,
          json: { detail: "Unexpected synthetic request" },
        });
      },
    );
    await page.goto("/finances/imports/batch-a?loan=loan-a");
    await expect(
      page.getByRole("heading", { name: "Harmonogram aktywowany" }),
    ).toBeVisible();
    await page
      .getByRole("combobox", { name: "Odczyt harmonogramu", exact: true })
      .selectOption("revision-new");
    await expect(
      page.getByRole("region", { name: "Porównanie odczytów źródła" }),
    ).toBeVisible();
    await page.getByLabel(/Sprawdziłem przypisanie/).check();
    await expect(
      page.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
    ).toBeDisabled();
    await page.getByLabel(/Porównałem odczyty/).check();
    await page
      .getByRole("button", { name: "Przygotuj podgląd harmonogramu" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Odczyt zgodny z zapisaną wersją" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Aktywuj harmonogram" }),
    ).toHaveCount(0);
    expect(
      await page.locator(".card").evaluateAll((nodes) =>
        nodes.every((node) => {
          const r = node.getBoundingClientRect();
          return r.left >= -1 && r.right <= innerWidth + 1;
        }),
      ),
    ).toBe(true);
    await page
      .getByRole("region", { name: "Porównanie odczytów źródła" })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: testInfo.outputPath(`reparse-comparison-${theme}.png`),
      fullPage: true,
    });
    expect(activations).toBe(0);
    expect(unexpected).toEqual([]);
    base.assertClean();
  });
}
