import { expect, test } from "@playwright/test";
import { financialDocumentFixtures, ids } from "./financial-document-fixtures";

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
    await expect(page.getByText("ten-sam-zakup.heif")).toBeVisible();
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
    await expect(
      page.getByRole("button", { name: "Zatwierdź do rejestru", exact: true }),
    ).toHaveCount(2);
    await page
      .getByRole("button", { name: "Zatwierdź do rejestru", exact: true })
      .last()
      .click();
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
