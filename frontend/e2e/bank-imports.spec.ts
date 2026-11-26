import { test, expect, type Page } from "@playwright/test";
import { fixtures } from "./fixtures";
import {
  batchFixture,
  rowFixture,
  previewFixture,
  receiptFixture,
  source,
} from "../src/test/bankImportFixtures";
import type {
  ImportBatch,
  ImportDecision,
  CommitResult,
} from "../src/api/bankImports";

async function importFixtures(
  page: Page,
  options: {
    lostReply?: boolean;
    sourceBlocked?: boolean;
    delayedReceipt?: boolean;
    initialBatch?: ImportBatch;
  } = {},
) {
  const base = await fixtures(page);
  let batch: ImportBatch = options.initialBatch ?? batchFixture({
    sources: [],
    groups: [],
    unresolved_count: 0,
  });
  let receipt: CommitResult | null = null;
  let canReadReceipt = !options.delayedReceipt;
  const mutations: { path: string; body: unknown; key: string | undefined }[] =
    [];
  const unexpected: string[] = [];
  await page.route("https://ui.test.invalid/api/finance/accounts", (route) =>
    route.fulfill({
      json: [
        {
          id: "account-pln",
          name: "Rachunek testowy",
          type: "checking",
          currency: "PLN",
          is_active: true,
        },
      ],
    }),
  );
  await page.route("https://ui.test.invalid/api/finance/categories", (route) =>
    route.fulfill({
      json: [
        { id: "category-a", name: "Zakupy", type: "expense", is_active: true },
      ],
    }),
  );
  await page.route(
    "https://ui.test.invalid/api/finance/imports**",
    async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const method = request.method();
      let body: unknown;
      if (method !== "GET") {
        body =
          request.headers()["content-type"]?.includes("application/json") &&
          request.postData()
            ? request.postDataJSON()
            : request.postData();
        mutations.push({
          path,
          body,
          key: request.headers()["idempotency-key"],
        });
      }
      if (method === "GET" && path.endsWith("/imports/auto-post-settings"))
        return route.fulfill({
          json: {
            enabled: false,
            expense_category_id: null,
            income_category_id: null,
          },
        });
      if (path.endsWith("/imports/history"))
        return route.fulfill({
          json: { items: [], total: 0, offset: 0, limit: 25 },
        });
      if (path === "/api/finance/imports")
        return route.fulfill({ json: method === "GET" ? [batch] : batch });
      if (method === "GET" && path.endsWith("/batch-a"))
        return route.fulfill({ json: batch });
      if (method === "GET" && path.endsWith("/rows"))
        return route.fulfill({
          json: {
            items: batch.sources.length
              ? [
                  {
                    ...rowFixture(),
                    decision: batch.groups[0]?.decision ?? null,
                  },
                ]
              : [],
            total: batch.sources.length ? 1 : 0,
            offset: 0,
            limit: 100,
          },
        });
      if (method === "POST" && path.endsWith("/sources")) {
        const duplicate = batch.sources.length > 0;
        batch = {
          ...batch,
          sources: [
            {
              ...source,
              validation_state: options.sourceBlocked ? "blocked" : "passed",
              checks: options.sourceBlocked
                ? [
                    {
                      code: "balance_rollforward",
                      required: true,
                      result: "failed",
                      expected: 900,
                      actual: 800,
                    },
                  ]
                : [...source.checks],
            },
          ],
          unresolved_count: 1,
        };
        return route.fulfill({
          json: {
            source: batch.sources[0],
            is_duplicate: duplicate,
            existing_batch_id: duplicate ? batch.id : null,
          },
        });
      }
      if (method === "POST" && path.endsWith("/prepare"))
        return route.fulfill({
          json: {
            id: "job-a",
            source_id: source.id,
            revision_id: "revision-a",
            state: "ready",
            attempt: 1,
            error_code: null,
          },
        });
      if (method === "PUT" && path.endsWith("/decisions")) {
        const data = body as {
          expected_version: number;
          decisions: ImportDecision[];
        };
        expect(data.expected_version).toBe(batch.version);
        batch = {
          ...batch,
          version: batch.version + 1,
          groups: data.decisions.map((decision) => ({
            id: decision.group_id,
            version: 1,
            state: decision.action === "defer" ? "deferred" : "ready",
            row_ids: decision.row_ids,
            decision,
          })),
        };
        return route.fulfill({ json: batch });
      }
      if (method === "POST" && path.endsWith("/preview"))
        return route.fulfill({
          json: {
            ...previewFixture(),
            version: batch.version,
            groups: [
              { ...previewFixture().groups[0], group_id: batch.groups[0].id },
            ],
          },
        });
      if (method === "POST" && path.endsWith("/commit")) {
        expect(body).toEqual({
          preview_id: "preview-a",
          request_hash: receiptFixture.request_hash,
        });
        receipt = receiptFixture;
        batch = {
          ...batch,
          version: batch.version + 1,
          commit_state: "committed",
          unresolved_count: 0,
          groups: batch.groups.map((group) => ({
            ...group,
            state: "committed",
          })),
        };
        if (options.lostReply) return route.abort("failed");
        return route.fulfill({ json: receipt });
      }
      if (method === "GET" && path.includes("/commands/"))
        return receipt && canReadReceipt
          ? route.fulfill({ json: receipt })
          : route.fulfill({ status: 404, json: { code: "command_not_found" } });
      unexpected.push(method + " " + path);
      return route.fulfill({
        status: 500,
        json: { detail: "Unexpected synthetic import request" },
      });
    },
  );
  return {
    mutations,
    releaseReceipt: () => {
      canReadReceipt = true;
    },
    assertClean: () => {
      base.assertClean();
      expect(unexpected).toEqual([]);
    },
    getBatch: () => batch,
  };
}

test("shows Velo card installment costs only for the active statement", async ({
  page,
}) => {
  const { mutations } = await importFixtures(page, {
    initialBatch: batchFixture({
      sources: [
        {
          ...source,
          checks: [...source.checks],
          warnings: [],
          layout: "velo_card_v1",
          candidate_revision_id: "candidate-a",
          candidate_parser_version: "v2",
          velo_card_breakdown: {
            due_date: "2026-04-14",
            cycle_debt_pln: 81059,
            minimum_pln: 79439,
            future_installment_principal_pln: 1125781,
            komfort_installment: {
              principal_pln: 74219,
              interest_pln: 2754,
              total_pln: 76973,
              included_in_minimum: true,
            },
            cash_interest_charges: [
              {
                row_key: "cash-interest",
                kind: "cash_interest",
                booking_date: "2026-03-17",
                amount_pln: 2466,
              },
            ],
            unassigned_installment_charges: [],
          },
        },
        {
          ...source,
          id: "incomplete-source",
          original_name: "Niepełny wyciąg.pdf",
          checks: [],
          warnings: [],
          layout: "velo_card_v1",
          velo_card_breakdown: {
            due_date: null,
            cycle_debt_pln: null,
            minimum_pln: null,
            future_installment_principal_pln: null,
            komfort_installment: null,
            cash_interest_charges: [],
            unassigned_installment_charges: [
              {
                row_key: "principal",
                kind: "principal",
                booking_date: "2026-03-17",
                amount_pln: 74219,
              },
            ],
          },
        },
      ],
    }),
  });
  await page.goto("/finances/imports/batch-a");
  await page.getByRole("button", { name: "statement.pdf", exact: true }).click();
  const breakdown = page.getByRole("region", {
    name: "Co składa się na spłatę karty",
  });
  await expect(breakdown.getByText("794,39 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText("14.04.2026")).toBeVisible();
  await expect(breakdown.getByText("810,59 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText(/11\s257,81 PLN/)).toBeVisible();
  await expect(breakdown.getByText("742,19 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText("27,54 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText("769,73 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText("24,66 PLN", { exact: true })).toBeVisible();
  await expect(breakdown.getByText(/Rata jest już ujęta/)).toBeVisible();
  await page.getByRole("button", { name: /Porównaj ponowny odczyt/ }).click();
  await expect(breakdown).toHaveCount(0);
  await page.getByRole("button", { name: "Wróć do bieżącego odczytu" }).click();
  await expect(breakdown).toBeVisible();
  await page.getByRole("button", { name: "Niepełny wyciąg.pdf", exact: true }).click();
  await expect(breakdown.getByText(/Brak jednoznacznego powiązania/)).toBeVisible();
  await expect(breakdown.getByText("Brak danych w odczycie").first()).toBeVisible();
  await expect(breakdown.getByText("Razem rata")).toHaveCount(0);
  expect(mutations).toEqual([]);
});

async function upload(page: Page) {
  await page.getByLabel("Pliki wyciągów").setInputFiles({
    name: "synthetic.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Rodzaj,Produkt,Data rozpoczęcia,Data zrealizowania,Opis,Kwota,Opłata,Waluta,State,Saldo\nPłatność kartą,Bieżący,2026-01-03 00:00:00,2026-01-03 00:00:00,Synthetic,-1.00,0.00,PLN,ZAKOŃCZONO,9.00\n",
    ),
  });
  await page.getByRole("button", { name: "Dodaj pliki" }).click();
  await expect(
    page.getByText(/synthetic.csv.*Wymaga sprawdzenia/),
  ).toBeVisible();
}

for (const mode of ["direct", "lost reply", "lost reply and reload"] as const) {
  const lostReply = mode !== "direct";
  const reload = mode === "lost reply and reload";
  test(`upload, deliberate decision, frozen confirmation and durable receipt${` (${mode})`}`, async ({
    page,
  }) => {
    const observed = await importFixtures(page, {
      lostReply,
      delayedReceipt: reload,
    });
    await page.goto("/finances/imports?account=account-pln");
    await upload(page);
    expect(
      observed.mutations.some((value) => value.path.endsWith("/commit")),
    ).toBe(false);
    await page.getByRole("link", { name: "Sprawdź import" }).click();
    await page.getByLabel("Wybierz wiersz Syntetyczny zakup").check();
    await page.getByLabel("Co zrobić z wierszem?").selectOption("create");
    await page.getByLabel("Rodzaj operacji").selectOption("expense");
    await expect(page.getByLabel("Rachunek źródłowy")).toHaveValue(
      "account-pln",
    );
    await page
      .getByRole("combobox", { name: "Kategoria", exact: true })
      .selectOption("category-a");
    await page.getByRole("button", { name: "Zapisz decyzję" }).click();
    await expect(
      page.getByRole("button", { name: "Przygotuj podgląd" }),
    ).toBeEnabled();
    await page.reload();
    await expect(page.getByLabel(/Wybierz grupę/)).toBeChecked();
    await page.getByRole("button", { name: "Przygotuj podgląd" }).click();
    const preview = page.getByRole("region", { name: "Podgląd zatwierdzenia" });
    const commit = preview.getByRole("button", {
      name: "Zatwierdź wybrane grupy",
    });
    await expect(commit).toBeDisabled();
    expect(
      observed.mutations.some((value) => value.path.endsWith("/commit")),
    ).toBe(false);
    await preview.getByRole("checkbox", { name: /Potwierdzam/ }).check();
    await commit.click();
    if (reload) {
      await expect(page.getByText(/Wynik zapisu jest nieznany/)).toBeVisible();
      observed.releaseReceipt();
      await page.reload();
    }
    await expect(
      page.getByRole("heading", { name: "Zapisano wynik importu" }),
    ).toBeVisible();
    const commits = observed.mutations.filter((value) =>
      value.path.endsWith("/commit"),
    );
    expect(commits).toHaveLength(1);
    expect(commits[0].key).toBeTruthy();
    expect(observed.getBatch().commit_state).toBe("committed");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    observed.assertClean();
  });
}

test("duplicate source opens its existing batch and source validation errors cannot be acknowledged into a commit", async ({
  page,
}) => {
  const observed = await importFixtures(page, { sourceBlocked: true });
  await page.goto("/finances/imports");
  await upload(page);
  await page.getByRole("button", { name: "Dodaj pliki" }).click();
  await expect(
    page.getByRole("link", { name: "Otwórz istniejący import" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Otwórz istniejący import" }).click();
  await expect(page.getByText(/Błąd kontroli źródła/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Przygotuj podgląd" }),
  ).toBeDisabled();
  expect(
    observed.mutations.filter((value) => value.path.endsWith("/prepare")),
  ).toHaveLength(1);
  expect(
    observed.mutations.filter((value) => value.path.endsWith("/commit")),
  ).toHaveLength(0);
  observed.assertClean();
});
