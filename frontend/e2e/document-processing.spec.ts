import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { fixtures } from "./fixtures";
import {
  processingDocument,
  processingReview,
} from "../src/test/documentFixtures";

const photoBytes = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAMCAIAAADQ/GvKAAAAFUlEQVR4nGP8//8/AzbAhFV0REsAAInrAxV4Pe4oAAAAAElFTkSuQmCC",
  "base64",
);

test("Today opens the camera picker and uploads the photo as a document", async ({
  page,
}) => {
  const base = await fixtures(page);
  const document = processingDocument({
    user_id: "qa",
    original_name: "zdjecie-faktury.png",
    mime_type: "image/png",
    status: "done",
    review: null,
  });
  let uploads = 0;
  await page.route("**/api/documents**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/documents/upload" && request.method() === "POST") {
      expect(request.postData()).toContain(
        'name="file"; filename="zdjecie-faktury.png"',
      );
      uploads += 1;
      return route.fulfill({ json: { document, is_duplicate: false } });
    }
    if (path === "/api/documents")
      return route.fulfill({ json: uploads ? [document] : [] });
    await route.fallback();
  });

  await page.goto("/today");
  const camera = page.getByRole("button", { name: "Zrób zdjęcie dokumentu" });
  await expect(camera).toHaveAccessibleDescription(
    /zdjęcie oraz nazwy i ścieżki kategorii/,
  );
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    camera.click(),
  ]);
  expect(await chooser.element().getAttribute("capture")).toBe("environment");
  expect(await chooser.element().getAttribute("accept")).toContain(
    "image/jpeg",
  );
  expect(uploads).toBe(0);
  await chooser.setFiles({
    name: "zdjecie-faktury.png",
    mimeType: "image/png",
    buffer: photoBytes,
  });
  const scan = page.getByRole("dialog", { name: "Podgląd skanu" });
  await expect(
    scan.getByRole("img", { name: "Podgląd zdjęcia dokumentu" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      scan
        .getByRole("img")
        .evaluate((image: HTMLImageElement) => image.naturalWidth),
    )
    .toBe(8);
  expect(uploads).toBe(0);
  await scan.getByRole("button", { name: "Wyślij zdjęcie" }).click();
  await expect(
    page.getByRole("list", { name: "Stan przesyłania" }),
  ).toContainText("Przesłano");
  await expect(page).toHaveURL(/\/today$/);
  expect(uploads).toBe(1);
  await page.getByRole("link", { name: "Otwórz dokumenty" }).click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(
    page.getByRole("button", { name: "Otwórz dokument: zdjecie-faktury.png" }),
  ).toBeVisible();
  expect(base.mutations).toEqual([]);
  await base.assertClean();
});

test("a scan can retake and reorder photos before uploading one PDF", async ({
  page,
}) => {
  const base = await fixtures(page);
  const uploads: string[][] = [];
  const document = processingDocument({
    user_id: "qa",
    original_name: "Skan dokumentu.pdf",
    mime_type: "application/pdf",
    review: null,
  });
  await page.route("**/api/documents/upload", async (route) => {
    const payload = route.request().postData() ?? "";
    uploads.push(
      [...payload.matchAll(/name="pages"; filename="([^"]+)"/g)].map(
        (match) => match[1],
      ),
    );
    return route.fulfill({ json: { document, is_duplicate: false } });
  });
  await page.goto("/today");
  for (const [action, name] of [
    ["Zrób zdjęcie dokumentu", "nieostre.png"],
    ["Powtórz zdjęcie", "pierwsza.png"],
    ["Dodaj stronę", "druga.png"],
  ]) {
    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.getByRole("button", { name: action, exact: true }).click(),
    ]);
    await chooser.setFiles({ name, mimeType: "image/png", buffer: photoBytes });
  }
  const scan = page.getByRole("dialog", { name: "Podgląd skanu" });
  await expect(scan.getByRole("button", { name: "Strona 2" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await scan.getByRole("button", { name: "Przesuń wcześniej" }).click();
  await expect(scan.getByRole("button", { name: "Strona 1" })).toHaveAttribute(
    "title",
    "druga.png",
  );
  expect(uploads).toEqual([]);
  await scan.getByRole("button", { name: "Wyślij jako PDF" }).click();
  await expect(
    page.getByRole("list", { name: "Stan przesyłania" }),
  ).toContainText("Skan dokumentu.pdf");
  expect(uploads).toEqual([["druga.png", "pierwsza.png"]]);
  await base.assertClean();
});

test("Today counters open separate document worklists", async ({ page }) => {
  const base = await fixtures(page);
  await page.route("**/api/documents/worklists", (route) =>
    route.fulfill({ json: { review: 1, errors: 1 } }),
  );
  await page.route("**/api/documents?**", async (route) => {
    const kind = new URL(route.request().url()).searchParams.get("worklist");
    if (!kind) return route.fallback();
    const document = processingDocument({
      original_name:
        kind === "review" ? "Gotowy odczyt.pdf" : "Uszkodzony odczyt.pdf",
      status: kind === "review" ? "done" : "error",
      review: null,
    });
    return route.fulfill({ json: [document] });
  });
  await page.goto("/today");
  const queues = page.getByRole("navigation", { name: "Kolejka dokumentów" });
  await queues.getByRole("link", { name: "Do sprawdzenia 1" }).click();
  await expect(page).toHaveURL(/worklist=review/);
  await expect(page.getByText("Gotowy odczyt.pdf")).toBeVisible();
  await page
    .getByRole("button", { name: "Błędy odczytu", exact: true })
    .click();
  await expect(page).toHaveURL(/worklist=errors/);
  await expect(page.getByText("Uszkodzony odczyt.pdf")).toBeVisible();
  await expect(page.getByText("Gotowy odczyt.pdf")).toHaveCount(0);
  await base.assertClean();
});

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
