import { expect, test } from "@playwright/test";
import { financialDocumentFixtures, ids } from "./financial-document-fixtures";

test("declaration persists, disappears from obligations, and later real links are not doubled", async ({
  page,
}) => {
  const api = await financialDocumentFixtures(page);
  await page.goto(`/finances/documents?bill=${ids.bill}`);
  await page
    .getByRole("button", {
      name: "Oznacz jako opłaconą bez transakcji",
      exact: true,
    })
    .click();
  const declaration = page.getByRole("dialog");
  await expect(
    declaration.getByText(/Nie powstanie transakcja ani wydatek/),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: test.info().outputPath("declaration-dialog.png"),
  });
  await declaration.getByRole("checkbox").check();
  await declaration
    .getByRole("button", { name: "Potwierdź oznaczenie" })
    .click();
  await expect(declaration).toHaveCount(0);
  await page.reload();
  const details = page.getByRole("region", { name: "Szczegóły dokumentu" });
  await expect(
    details.getByText("Opłacona deklaracyjnie — bez powiązania z księgą"),
  ).toBeVisible();
  await expect(
    details.locator("dt", { hasText: /^Do zapłaty$/ }).locator(".."),
  ).toContainText("0,00");
  await expect(
    details
      .locator("dt", { hasText: "Pozostało do powiązania z księgą" })
      .locator(".."),
  ).toContainText("100,00");
  expect(api.mutations.map(({ path }) => path)).toEqual([
    `/api/finance/bills/${ids.bill}/payment-declaration`,
  ]);
  await page.goto("/finances/cashflow");
  await expect(page.getByText("Faktura 100 — listopad")).toHaveCount(0);
  await page.goto(`/finances/documents?bill=${ids.bill}`);
  for (const amount of ["40.00", "60.00"]) {
    await page
      .getByRole("button", { name: "Powiąż płatność", exact: true })
      .click();
    const payment = page.getByRole("dialog", { name: "Rozlicz płatność" });
    await payment.getByLabel("Kwota (PLN)").fill(amount);
    await payment.getByRole("radio").check();
    await payment
      .getByRole("button", { name: "Powiąż płatność", exact: true })
      .click();
    await expect(payment).toHaveCount(0);
  }
  await expect(details.getByText("Rozliczona z księgą")).toBeVisible();
  expect(api.mutations.map(({ path }) => path)).toEqual([
    `/api/finance/bills/${ids.bill}/payment-declaration`,
    `/api/finance/bills/${ids.bill}/allocations`,
    `/api/finance/bills/${ids.bill}/allocations`,
  ]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  api.assertClean();
});

test("undo after a partial real link restores only the remaining obligation", async ({
  page,
}) => {
  const api = await financialDocumentFixtures(page);
  await page.goto(`/finances/documents?bill=${ids.bill}`);
  await page
    .getByRole("button", { name: "Powiąż płatność", exact: true })
    .click();
  const payment = page.getByRole("dialog", { name: "Rozlicz płatność" });
  await payment.getByLabel("Kwota (PLN)").fill("40.00");
  await payment.getByRole("radio").check();
  await payment
    .getByRole("button", { name: "Powiąż płatność", exact: true })
    .click();
  await expect(payment).toHaveCount(0);
  await page
    .getByRole("button", {
      name: "Oznacz jako opłaconą bez transakcji",
      exact: true,
    })
    .click();
  let dialog = page.getByRole("dialog");
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Potwierdź oznaczenie" }).click();
  await expect(dialog).toHaveCount(0);
  await page
    .getByRole("button", { name: "Cofnij oznaczenie opłacenia", exact: true })
    .click();
  dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText(/Przywracasz do zapłaty pozostałe 60,00/),
  ).toBeVisible();
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Przywróć do zapłaty" }).click();
  await expect(dialog).toHaveCount(0);
  await page.goto("/finances/cashflow");
  const row = page.getByText("Faktura 100 — listopad");
  await expect(row).toHaveCount(1);
  await expect(row.locator("..")).toContainText("60,00 PLN");
  expect(
    api.mutations.filter(({ path }) => path.endsWith("/payment-declaration")),
  ).toHaveLength(2);
  expect(
    api.mutations.filter(({ path }) => path.endsWith("/payments")),
  ).toHaveLength(0);
  api.assertClean();
});

for (const viewport of [375, 1440]) {
  test(`matching evidence and stale selection never creates a transaction at ${viewport}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport, height: 900 });
    const api = await financialDocumentFixtures(page, {
      candidateEvidence: true,
    });
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/finance/bills/*/candidates**", async (route) => {
      if (new URL(route.request().url()).searchParams.has("query")) await held;
      await route.fallback();
    });
    await page.goto(`/finances/documents?bill=${ids.bill}`);
    await page
      .getByRole("button", { name: "Powiąż płatność", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "Rozlicz płatność" });
    await expect(dialog.getByText(/Zakup: 2026-10-30.*ręcznie/)).toBeVisible();
    await expect(
      dialog.getByText(/Księgowanie: 2026-11-02.*bank/),
    ).toBeVisible();
    await expect(
      dialog.getByText(
        "Nazwa sprzedawcy z dokumentu występuje w opisie płatności",
      ),
    ).toBeVisible();
    await expect(dialog.getByRole("radio")).not.toBeChecked();
    await dialog.getByRole("radio").check();
    await dialog.getByLabel("Szukaj istniejącej płatności").fill("dostawca");
    await expect(dialog.getByRole("status")).toHaveText(/Pobieranie/);
    await expect(
      dialog.getByRole("button", { name: "Powiąż płatność", exact: true }),
    ).toBeDisabled();
    expect(api.mutations).toHaveLength(0);
    release();
    await expect(dialog.getByRole("radio")).not.toBeChecked();
    await dialog.getByRole("radio").check();
    await dialog.getByLabel("Kwota (PLN)").fill("40.00");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await dialog
      .getByRole("button", { name: "Powiąż płatność", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    expect(
      api.mutations.map(({ method, path, body }) => ({ method, path, body })),
    ).toEqual([
      {
        method: "POST",
        path: `/api/finance/bills/${ids.bill}/allocations`,
        body: { version: 2, posting_id: ids.posting40, amount_minor: 4000 },
      },
    ]);
    api.assertClean();
  });

  test(`candidate error and empty are distinct and never become a new expense at ${viewport}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport, height: 900 });
    const api = await financialDocumentFixtures(page);
    let fail = true;
    await page.route("**/api/finance/bills/*/candidates**", (route) =>
      fail
        ? route.fulfill({ status: 500, json: { detail: "synthetic_failure" } })
        : route.fulfill({
            json: { items: [], total: 0, limit: 20, offset: 0 },
          }),
    );
    await page.goto(`/finances/documents?bill=${ids.bill}`);
    await page
      .getByRole("button", { name: "Powiąż płatność", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "Rozlicz płatność" });
    await expect(dialog.getByRole("alert")).toHaveText(
      /Nie udało się pobrać płatności/,
    );
    fail = false;
    await dialog.getByRole("button", { name: "Spróbuj ponownie" }).click();
    await expect(
      dialog.getByText("Brak płatności w wybranych filtrach."),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Powiąż płatność", exact: true }),
    ).toBeDisabled();
    expect(api.mutations).toHaveLength(0);
    api.assertClean();
  });
}

for (const viewport of [375, 1440]) {
  test(`financial-document allocation and explicit forecast replacement at ${viewport}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport, height: 900 });
    const api = await financialDocumentFixtures(page);
    await page.goto(`/finances/documents?bill=${ids.bill}`);
    await expect(
      page.getByRole("heading", { name: "Stary dostawca" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Wpływ na prognozę" }).click();
    await page.getByRole("radio").check();
    await page.getByRole("button", { name: "Zastąp estymatę" }).click();
    await expect(
      page.getByText("Faktura zastępuje wystąpienie 2026-11-05."),
    ).toHaveCount(0);

    for (const amount of ["40.00", "60.00"]) {
      await page
        .getByRole("button", { name: "Powiąż płatność", exact: true })
        .click();
      await page.getByLabel("Kwota (PLN)").fill(amount);
      await page.getByRole("radio").check();
      await page
        .getByRole("button", { name: "Powiąż płatność", exact: true })
        .last()
        .click();
      await expect(
        page.getByRole("dialog", { name: "Rozlicz płatność" }),
      ).toHaveCount(0);
    }
    await expect(
      page.locator("dt", { hasText: "Uzgodnienie" }).locator(".."),
    ).toContainText("full");
    expect(
      api.mutations.map(({ method, path }) => `${method} ${path}`),
    ).toEqual([
      `POST /api/finance/bills/${ids.bill}/coverage`,
      `POST /api/finance/bills/${ids.bill}/allocations`,
      `POST /api/finance/bills/${ids.bill}/allocations`,
    ]);
    api.assertClean();
  });
}

test("replacing one 100 PLN occurrence leaves exactly one 120 PLN invoice upcoming", async ({
  page,
}) => {
  const api = await financialDocumentFixtures(page, {
    invoiceTotalMinor: 12000,
  });
  await page.goto("/finances/cashflow");
  await expect(page.getByText("Faktura 120 — listopad")).toHaveCount(1);
  await expect(page.getByText("Abonament — listopad")).toBeVisible();

  await page.goto(`/finances/documents?bill=${ids.bill}`);
  await page.getByRole("button", { name: "Wpływ na prognozę" }).click();
  await expect(page.getByText("Wybierz konkretne wystąpienie.")).toBeVisible();
  await expect(page.getByText(/estymata 100\.00 PLN/)).toBeVisible();
  await page.getByRole("radio").check();
  await page.getByRole("button", { name: "Zastąp estymatę" }).click();

  await page.goto("/finances/cashflow");
  const invoice = page.getByText("Faktura 120 — listopad");
  await expect(invoice).toHaveCount(1);
  await expect(invoice.locator("..")).toContainText("120,00 PLN");
  await expect(page.getByText("Abonament — listopad")).toHaveCount(0);
  await expect(page.getByText("Abonament — grudzień")).toBeVisible();
  api.assertClean();
});

test("legacy PDF review remains manually usable after LLM/OCR error", async ({
  page,
}) => {
  const api = await financialDocumentFixtures(page, { reviewError: true });
  await page.goto("/documents");
  await page
    .getByRole("button", { name: "Otwórz dokument: stara-faktura.pdf" })
    .click();
  await page.getByRole("button", { name: "Sprawdź dane" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Możesz uzupełnić pola ręcznie",
  );
  await page.getByLabel("Sprzedawca").fill("Ręczny dostawca");
  await page.getByLabel("Opis").fill("Ręczny opis");
  await page.getByLabel("Kwota").fill("100.00");
  await page
    .getByRole("button", { name: "Zatwierdź do rejestru", exact: true })
    .click();
  const resolvedApproval = page.locator('button[type="button"]', {
    hasText: "Zatwierdź do rejestru",
  });
  await expect(resolvedApproval).toBeVisible();
  await resolvedApproval.click();
  await expect(page).toHaveURL(/\/finances\/documents\?bill=/);
  expect(
    api.mutations.some(
      ({ path }) => path === `/api/finance/bills/prepare/${ids.oldPdf}`,
    ),
  ).toBe(true);
  api.assertClean();
});

for (const viewport of [375, 1440]) {
  test(`synthetic HEIF upload attaches a second original without a cost at ${viewport}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport, height: 900 });
    const api = await financialDocumentFixtures(page);
    await page.goto("/documents");
    const chooser = page.locator('input[type="file"]').first();
    await expect(page.getByText(/HEIF — do 20\.0 MB/)).toBeVisible();
    await expect(chooser).toHaveAttribute("accept", /image\/heif/);
    await chooser.setInputFiles({
      name: "ten-sam-zakup.heif",
      mimeType: "image/heif",
      // Minimal synthetic ISO-BMFF HEIF marker; the browser need not decode it.
      buffer: Buffer.from([
        0,
        0,
        0,
        24,
        ...Buffer.from("ftypheic"),
        0,
        0,
        0,
        0,
        ...Buffer.from("mif1"),
      ]),
    });
    await expect(
      page
        .getByRole("list", { name: "Stan przesyłania" })
        .getByText("ten-sam-zakup.heif"),
    ).toBeVisible();
    await expect(page.getByText("Przesłano")).toBeVisible();
    await page
      .getByRole("button", { name: "Otwórz dokument: ten-sam-zakup.heif" })
      .click();
    await page.getByRole("button", { name: "Sprawdź dane" }).click();
    await page
      .getByRole("button", { name: "Zatwierdź do rejestru", exact: true })
      .click();
    await expect(page.getByText("Znaleziono podobny dokument.")).toBeVisible();
    await page.getByRole("button", { name: "Dołącz do istniejącego" }).click();
    await page.getByRole("button", { name: "Potwierdź dołączenie" }).click();
    await expect(page).toHaveURL(
      new RegExp(`/finances/documents\\?bill=${ids.bill}`),
    );
    expect(
      api.mutations.map(({ method, path }) => `${method} ${path}`),
    ).toEqual([
      "POST /api/documents/upload",
      `POST /api/finance/bills/prepare/${ids.heic}`,
      `POST /api/finance/bills/${ids.bill}/sources/${ids.heic}`,
    ]);
    api.assertClean();
  });

  test(`declared-paid receipt remains unreconciled without fake allocation at ${viewport}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport, height: 900 });
    const api = await financialDocumentFixtures(page);
    await page.goto("/documents");
    await page
      .getByRole("button", { name: "Otwórz dokument: paragon.pdf" })
      .click();
    await page.getByRole("button", { name: "Sprawdź dane" }).click();
    await page
      .getByRole("button", { name: "Zatwierdź do rejestru", exact: true })
      .click();
    const resolvedApproval = page.locator('button[type="button"]', {
      hasText: "Zatwierdź do rejestru",
    });
    await expect(resolvedApproval).toBeVisible();
    await resolvedApproval.click();
    await expect(page).toHaveURL(/\/finances\/documents\?bill=receipt-bill/);
    await expect(
      page.locator("dt", { hasText: "Uzgodnienie" }).locator(".."),
    ).toContainText("none");
    await expect(
      page
        .getByLabel("Szczegóły dokumentu")
        .locator("dt", { hasText: "Pozostało" })
        .locator(".."),
    ).toContainText("10,00");
    expect(api.isReceiptApproved()).toBe(true);
    expect(api.mutations.map(({ path }) => path)).toEqual([
      `/api/finance/bills/prepare/${ids.receipt}`,
      "/api/finance/bills/receipt-draft/approve",
    ]);
    api.assertClean();
  });
}
