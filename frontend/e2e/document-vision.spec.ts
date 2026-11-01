import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { documentVisionFixtures, visionIds } from "./document-vision-fixtures";

for (const viewport of [375, 1440]) {
  for (const colorScheme of ["light", "dark"] as const) {
    test(`vision review preserves dirty human fields at ${viewport}px ${colorScheme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: viewport, height: 850 });
      await page.emulateMedia({ colorScheme });
      const api = await documentVisionFixtures(page);
      await page.goto("/documents");
      await page
        .getByRole("button", { name: "Otwórz dokument: synthetic-photo.jpg" })
        .click();
      await page.getByRole("button", { name: "Sprawdź dane" }).click();
      await expect(
        page.getByRole("dialog", { name: "Sprawdź dane dokumentu" }),
      ).toBeVisible();
      await page.getByLabel("Kwota").fill("99.99");
      await page.getByLabel("Konto płatności").selectOption("a1");
      await page.getByLabel("Kategoria").selectOption("c1");
      await expect(page.getByLabel("Sprzedawca")).toHaveValue("Delayed shop", {
        timeout: 6_000,
      });
      await expect(page.getByLabel("Kwota")).toHaveValue("99.99");
      await expect(page.getByLabel("Konto płatności")).toHaveValue("a1");
      await expect(page.getByLabel("Kategoria")).toHaveValue("c1");
      await expect(page.getByLabel("Waluta")).toHaveValue("");
      await expect(
        page.getByRole("button", { name: "Zatwierdź do rejestru" }),
      ).toBeDisabled();
      expect(
        await new AxeBuilder({ page }).include("[role=dialog]").analyze(),
      ).toEqual(expect.objectContaining({ violations: [] }));
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(
        page.getByRole("button", {
          name: "Otwórz dokument: synthetic-photo.jpg",
        }),
      ).toBeFocused();
      await expect(
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      ).resolves.toBe(true);
      expect(api.requests).toEqual([]);
      api.assertClean();
    });
  }
}

test("error, limit, and refusal retain private original and require explicit distinct actions", async ({
  page,
}) => {
  const api = await documentVisionFixtures(page, {
    error: "vision_daily_limit",
  });
  await page.goto("/documents");
  await page
    .getByRole("button", { name: "Otwórz dokument: synthetic-photo.jpg" })
    .click();
  await page.getByRole("button", { name: "Sprawdź dane" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Możesz uzupełnić pola ręcznie",
  );
  await page.getByRole("button", { name: "Ponów AI" }).click();
  await page.getByRole("button", { name: "Ponów lokalny OCR" }).click();
  expect(api.requests).toEqual([
    `POST /api/documents/${visionIds.image}/vision/prepare`,
    `POST /api/documents/${visionIds.image}/retry-ocr`,
  ]);
  api.assertClean();
});

test("synthetic JPEG upload posts multipart and its pending vision review becomes ready", async ({
  page,
}) => {
  const api = await documentVisionFixtures(page);
  await page.goto("/documents");
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "synthetic-upload.jpg",
      mimeType: "image/jpeg",
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
  await expect(
    page.getByRole("status", { name: "" }).filter({ hasText: "Przesłano" }),
  ).toBeVisible();
  expect(api.uploadRequests).toHaveLength(1);
  expect(api.uploadRequests[0].headers["content-type"]).toContain(
    "multipart/form-data",
  );
  expect(api.uploadRequests[0].body?.toString()).toContain(
    "synthetic-upload.jpg",
  );
  await page
    .getByRole("button", { name: "Otwórz dokument: synthetic-upload.jpg" })
    .click();
  await page.getByRole("button", { name: "Sprawdź dane" }).click();
  await expect(page.getByLabel("Sprzedawca")).toHaveValue("");
  await expect(page.getByLabel("Sprzedawca")).toHaveValue("Delayed shop", {
    timeout: 6_000,
  });
  api.assertClean();
});

test("review fetches binary private preview and original and offers a download link", async ({
  page,
}) => {
  const api = await documentVisionFixtures(page);
  await page.goto("/documents");
  await page
    .getByRole("button", { name: "Otwórz dokument: synthetic-photo.jpg" })
    .click();
  const previewResponse = page.waitForResponse((response) =>
    response.url().endsWith(`/documents/${visionIds.image}/preview`),
  );
  const originalResponse = page.waitForResponse((response) =>
    response.url().endsWith(`/documents/${visionIds.image}/original`),
  );
  await page.getByRole("button", { name: "Sprawdź dane" }).click();
  expect((await previewResponse).status()).toBe(200);
  expect(await (await originalResponse).body()).toEqual(
    Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  );
  await expect(
    page.getByRole("link", { name: "Pobierz autoryzowany oryginał" }),
  ).toHaveAttribute("download", "dokument");
  expect(api.privateRequests.map(({ path }) => path)).toEqual([
    `/api/documents/${visionIds.image}/preview`,
    `/api/documents/${visionIds.image}/original`,
  ]);
  expect(
    api.privateRequests.every(({ headers }) => headers.accept !== undefined),
  ).toBe(true);
  api.assertClean();
});

test("HTTP 429 from an explicit vision retry leaves manual fields available", async ({
  page,
}) => {
  const api = await documentVisionFixtures(page, {
    error: "vision_daily_limit",
    visionRetryStatus: 429,
  });
  await page.goto("/documents");
  await page
    .getByRole("button", { name: "Otwórz dokument: synthetic-photo.jpg" })
    .click();
  await page.getByRole("button", { name: "Sprawdź dane" }).click();
  await expect(page.getByLabel("Sprzedawca")).toBeVisible();
  await page.getByLabel("Sprzedawca").fill("Ręcznie wpisany sprzedawca");
  await page.getByRole("button", { name: "Ponów AI" }).click();
  await expect(
    page.getByText("Nie udało się ponowić AI. Możesz poprawić pola ręcznie.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByLabel("Sprzedawca")).toHaveValue(
    "Ręcznie wpisany sprzedawca",
  );
  expect(api.requests).toEqual([
    `POST /api/documents/${visionIds.image}/vision/prepare`,
  ]);
  api.assertClean();
});

test("legacy PDF retains its text-review contract without a vision request", async ({
  page,
}) => {
  const api = await documentVisionFixtures(page);
  await page.goto("/documents");
  await page
    .getByRole("button", { name: "Otwórz dokument: legacy.pdf" })
    .click();
  await page.getByRole("button", { name: "Sprawdź dane" }).click();
  await expect(page.getByLabel("Sprzedawca")).toHaveValue("Legacy");
  expect(api.requests).toEqual([]);
  api.assertClean();
});
