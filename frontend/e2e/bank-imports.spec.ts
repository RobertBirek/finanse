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
  options: { lostReply?: boolean; sourceBlocked?: boolean } = {},
) {
  const base = await fixtures(page);
  let batch: ImportBatch = batchFixture({
    sources: [],
    groups: [],
    unresolved_count: 0,
  });
  let receipt: CommitResult | null = null;
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
        return receipt
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
    assertClean: () => {
      base.assertClean();
      expect(unexpected).toEqual([]);
    },
    getBatch: () => batch,
  };
}

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

for (const lostReply of [false, true]) {
  test(`upload, deliberate decision, frozen confirmation and durable receipt${lostReply ? " after a lost reply" : ""}`, async ({
    page,
  }) => {
    const observed = await importFixtures(page, { lostReply });
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
