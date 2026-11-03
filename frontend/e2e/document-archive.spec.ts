import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { financialDocumentFixtures, ids } from "./financial-document-fixtures";
import {
  processingDocument,
  processingReview,
} from "../src/test/documentFixtures";

async function archiveFixture(
  page: Page,
  { initialArchived = false, busy = false } = {},
) {
  const base = await financialDocumentFixtures(page);
  let archived = initialArchived;
  const writes: string[] = [];
  const doc = processingDocument({
    id: ids.oldPdf,
    user_id: "qa",
    original_name: "synthetic-original.pdf",
    mime_type: "application/pdf",
    processing_method: "legacy_ocr",
    review: null,
  });
  if (busy) {
    doc.processing_method = "vision";
    doc.local_ocr_state = "processing";
    doc.local_ocr_job_id = "synthetic-ocr-job";
  }
  const response = () => ({
    ...doc,
    archived_at: archived ? "2026-11-03T12:00:00Z" : null,
  });
  await page.route("**/api/documents**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname,
      method = route.request().method();
    if (path === "/api/documents/active") return route.fulfill({ json: [] });
    if (path === "/api/documents")
      return route.fulfill({
        json:
          (url.searchParams.get("archived") === "true") === archived
            ? [response()]
            : [],
      });
    if (path === `/api/documents/${doc.id}`)
      return route.fulfill({ json: response() });
    if (
      path === `/api/documents/${doc.id}/original` ||
      path === `/api/documents/${doc.id}/preview`
    )
      return route.fulfill({
        contentType: "application/pdf",
        headers: { "Cache-Control": "private, no-store" },
        body: Buffer.from("%PDF-1.4\nsynthetic retained evidence\n%%EOF"),
      });
    if (path === `/api/documents/${doc.id}/review`)
      return route.fulfill({
        json: processingReview({ document_id: doc.id, status: "ready" }),
      });
    if (method === "POST" && path === `/api/documents/${doc.id}/archive`) {
      writes.push("archive");
      if (busy)
        return route.fulfill({
          status: 409,
          json: {
            code: "document_processing_active",
            detail: "document_processing_active",
          },
        });
      archived = true;
      return route.fulfill({ json: response() });
    }
    if (method === "POST" && path === `/api/documents/${doc.id}/restore`) {
      writes.push("restore");
      archived = false;
      return route.fulfill({ json: response() });
    }
    if (method === "POST" && path === "/api/documents/upload") {
      writes.push("upload");
      return route.fulfill({
        json: { document: response(), is_duplicate: true },
      });
    }
    await route.fallback();
  });
  page.on("dialog", (dialog) => dialog.accept());
  return { base, writes, doc };
}

test("archive and restore retain approved financial source and original", async ({
  page,
}, testInfo) => {
  const { base, writes, doc } = await archiveFixture(page);
  await page.goto("/documents");
  const before = await page.evaluate(
    async (id) => (await fetch(`/api/finance/bills/${id}`)).json(),
    ids.bill,
  );
  await page
    .getByRole("button", { name: `Archiwizuj dokument: ${doc.original_name}` })
    .click();
  await expect(
    page.getByText("Dokument przeniesiony do archiwum."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: `Otwórz dokument: ${doc.original_name}` }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Archiwum", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: `Przywróć dokument: ${doc.original_name}`,
    }),
  ).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).include("#main-content").analyze())
      .violations,
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("document-archive.png") });
  await page.goto(`/finances/documents?bill=${ids.bill}`);
  const detail = page.getByRole("region", { name: "Szczegóły dokumentu" });
  await expect(
    detail.getByRole("link", { name: "Oryginał", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await detail.getByRole("link", { name: "Oryginał", exact: true }).click();
  await download;
  const after = await page.evaluate(
    async (id) => (await fetch(`/api/finance/bills/${id}`)).json(),
    ids.bill,
  );
  expect(after).toEqual(before);
  await page.goto("/documents?archived=true");
  await page
    .getByRole("button", { name: `Przywróć dokument: ${doc.original_name}` })
    .click();
  await expect(page.getByText("Dokument przywrócony.")).toBeVisible();
  await page.getByRole("button", { name: "Aktywne", exact: true }).click();
  await expect(
    page.getByRole("button", { name: `Otwórz dokument: ${doc.original_name}` }),
  ).toBeVisible();
  expect(writes).toEqual(["archive", "restore"]);
  expect(base.mutations).toEqual([]);
  await base.assertClean();
});

test("active work explains archive rejection without changing the document", async ({
  page,
}) => {
  const { base, writes, doc } = await archiveFixture(page, { busy: true });
  await page.goto("/documents");
  await page
    .getByRole("button", { name: `Archiwizuj dokument: ${doc.original_name}` })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Dokument jest przetwarzany. Poczekaj na zakończenie odczytu AI/OCR.",
  );
  await expect(
    page.getByRole("button", { name: `Otwórz dokument: ${doc.original_name}` }),
  ).toBeVisible();
  expect(writes).toEqual(["archive"]);
  expect(base.mutations).toEqual([]);
  await base.assertClean();
});

test("archived duplicate upload requires explicit restore and never triggers AI", async ({
  page,
}) => {
  const { base, writes } = await archiveFixture(page, {
    initialArchived: true,
  });
  await page.goto("/documents");
  await page.locator('input[type="file"]:not([capture])').setInputFiles({
    name: "synthetic-copy.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from("synthetic-mocked-upload"),
  });
  await expect(
    page.getByText("Ten plik jest już w archiwum. Możesz go przywrócić."),
  ).toBeVisible();
  expect(writes).toEqual(["upload"]);
  await page.getByRole("button", { name: "Przywróć", exact: true }).click();
  await expect(page.getByText("Dokument przywrócony.")).toBeVisible();
  expect(writes).toEqual(["upload", "restore"]);
  expect(base.mutations).toEqual([]);
  await base.assertClean();
});
