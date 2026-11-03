import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { fixtures } from "./fixtures";
import {
  processingDocument,
  processingReview,
} from "../src/test/documentFixtures";

for (const kind of ["ai", "ocr"] as const) {
  test(`${kind} completion survives navigation and opens an off-page document`, async ({
    page,
  }, testInfo) => {
    const base = await fixtures(page);
    const doc = processingDocument({
      user_id: "qa",
      local_ocr_job_id: kind === "ocr" ? "ocr-job" : null,
      local_ocr_state: kind === "ocr" ? "processing" : null,
    });
    if (kind === "ocr")
      doc.review = { ...doc.review!, status: "ready", job_state: "succeeded" };
    let complete = false;
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/api/documents**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/documents/active")
        return route.fulfill({ json: complete ? [] : [doc] });
      if (path === "/api/documents") return route.fulfill({ json: [] });
      if (path === `/api/documents/${doc.id}`)
        return route.fulfill({
          json: complete
            ? {
                ...doc,
                local_ocr_state: kind === "ocr" ? "succeeded" : null,
                review: {
                  ...doc.review!,
                  status: "ready",
                  job_state: "succeeded",
                },
              }
            : doc,
        });
      if (path === `/api/documents/${doc.id}/review`)
        return route.fulfill({ json: processingReview({ status: "ready" }) });
      if (path.endsWith("/original") || path.endsWith("/preview"))
        return route.fulfill({ status: 404 });
      await route.fallback();
    });
    await page.goto("/documents");
    await expect(page.getByLabel("Przetwarzanie dokumentów")).toContainText(
      kind === "ai" ? "AI pracuje" : "OCR pracuje",
    );
    await page.locator('a[href="/today"]:visible').first().click();
    await expect(page).toHaveURL(/\/today$/);
    complete = true;
    const message =
      kind === "ai"
        ? "Propozycja z AI gotowa — sprawdź dane."
        : "OCR zakończony — sprawdź odczyt.";
    await expect(page.getByText(message)).toBeVisible({ timeout: 10000 });
    await expect(page.getByLabel("Przetwarzanie dokumentów")).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "Otwórz dokument" }),
    ).toHaveCount(1);
    await page.screenshot({ path: testInfo.outputPath(`${kind}-toast.png`) });
    await page.getByRole("link", { name: "Otwórz dokument" }).click();
    const dialog = page.getByRole("dialog", { name: "Sprawdź dane dokumentu" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Sprzedawca")).toHaveValue("Synthetic");
    await expect(
      dialog.getByRole("region", { name: "Powiadomienia o odczycie" }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Zamknij powiadomienie" }),
    ).toBeVisible();
    expect(
      (await new AxeBuilder({ page }).include("dialog[open]").analyze())
        .violations,
    ).toEqual([]);
    await dialog.getByRole("button", { name: "Zamknij powiadomienie" }).click();
    await expect(page.getByText(message)).toHaveCount(0);
    await dialog.getByRole("button", { name: "Zamknij", exact: true }).click();
    await expect(page).toHaveURL(/\/documents$/);
    expect(errors).toEqual([]);
    expect(base.mutations).toEqual([]);
    await base.assertClean();
  });
}
