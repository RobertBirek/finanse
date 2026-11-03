import { expect, type Page } from "@playwright/test";
import { fixtures } from "./fixtures";

export const visionIds = {
  image: "d8000000-0000-0000-0000-000000000001",
  pdf: "d8000000-0000-0000-0000-000000000002",
  upload: "d8000000-0000-0000-0000-000000000003",
};

const blankFields = {
  supplier_name: null,
  supplier_tax_id: null,
  number: null,
  issue_date: null,
  sale_date: null,
  due_date: null,
  description: null,
  payee_iban: null,
  total: null,
  currency: null,
};

/** Stateful fake API around the production dist; unregistered writes fail loudly. */
export async function documentVisionFixtures(
  page: Page,
  options: {
    error?:
      "provider_unavailable" | "vision_daily_limit" | "invalid_model_output";
    visionRetryStatus?: 429;
  } = {},
) {
  const base = await fixtures(page);
  const requests: string[] = [];
  const privateRequests: { path: string; headers: Record<string, string> }[] =
    [];
  const uploadRequests: {
    headers: Record<string, string>;
    body: Buffer | null;
  }[] = [];
  const reviewCalls = new Map<string, number>();
  const reviewId = (id: string) => id.replace(/^d/, "f");
  const document = (
    id: string,
    name: string,
    mime: string,
    vision = false,
  ) => ({
    id,
    original_name: name,
    filename: name,
    mime_type: mime,
    size_bytes: 12,
    created_at: "2026-11-01T08:00:00Z",
    updated_at: "2026-11-01T08:00:00Z",
    user_id: "qa",
    sha256_hash: id.slice(1).padEnd(64, "0"),
    status: "done",
    attempt_count: 1,
    next_attempt_at: null,
    last_error_code: null,
    processing_method: vision ? "vision" : "legacy_ocr",
    has_extracted_text: !vision,
    local_ocr_state: null as string | null,
    local_ocr_job_id: null as string | null,
    review: vision
      ? {
          revision_id: reviewId(id),
          revision: 1,
          input_method: "image",
          status: options.error ? "error" : "pending",
          error_code: options.error ?? null,
          warnings: [],
          job_state: options.error ? "failed" : "processing",
        }
      : null,
  });
  const docs = [
    document(visionIds.image, "synthetic-photo.jpg", "image/jpeg", true),
    document(visionIds.pdf, "legacy.pdf", "application/pdf"),
  ];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === "/api/documents" && method === "GET")
      return route.fulfill({ json: docs });
    const statusDocument = docs.find(
      (doc) => path === `/api/documents/${doc.id}`,
    );
    if (statusDocument && method === "GET") {
      const ready =
        (reviewCalls.get(statusDocument.id) ?? 0) > 1 && !options.error;
      return route.fulfill({
        json: {
          ...statusDocument,
          review:
            ready && statusDocument.review
              ? {
                  ...statusDocument.review,
                  status: "ready",
                  job_state: "succeeded",
                }
              : statusDocument.review,
        },
      });
    }
    if (path === "/api/documents/upload-capabilities")
      return route.fulfill({
        json: {
          max_file_bytes: 1024,
          accepted_mime_types: ["application/pdf", "image/jpeg"],
          automatic_image_vision: true,
          vision_provider_label: "test",
          vision_notice: "Human review required",
        },
      });
    if (path === `/api/documents/${visionIds.image}/preview`) {
      privateRequests.push({ path, headers: request.headers() });
      return route.fulfill({
        headers: { "Cache-Control": "private, no-store" },
        contentType: "image/jpeg",
        body: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
      });
    }
    if (path === `/api/documents/${visionIds.image}/original`) {
      privateRequests.push({ path, headers: request.headers() });
      return route.fulfill({
        headers: { "Cache-Control": "private, no-store" },
        contentType: "image/jpeg",
        body: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
      });
    }
    if (path.includes("/preview") || path.includes("/original"))
      return route.fulfill({ status: 404 });
    if (path === `/api/documents/${visionIds.image}/text`)
      return route.fulfill({ status: 404, json: { detail: "No OCR text" } });
    if (path === `/api/documents/${visionIds.pdf}/text`)
      return route.fulfill({
        json: {
          id: "t",
          document_id: visionIds.pdf,
          extracted_text: "Synthetic legacy PDF",
          ocr_engine: "fixture",
          extracted_at: null,
          created_at: "2026-11-01T08:00:00Z",
        },
      });
    const reviewMatch = path.match(/^\/api\/documents\/([^/]+)\/review$/);
    if (
      method === "GET" &&
      reviewMatch &&
      [visionIds.image, visionIds.upload].includes(reviewMatch[1])
    ) {
      const documentId = reviewMatch[1];
      const calls = (reviewCalls.get(documentId) ?? 0) + 1;
      reviewCalls.set(documentId, calls);
      const isImage = documentId === visionIds.image;
      const ready = calls > 1 && (!isImage || !options.error);
      return route.fulfill({
        json: {
          id: reviewId(documentId),
          document_id: documentId,
          revision: 1,
          input_method: "image",
          status:
            isImage && options.error ? "error" : ready ? "ready" : "pending",
          error_code: isImage ? (options.error ?? null) : null,
          document_type: "receipt",
          fields: ready
            ? {
                ...blankFields,
                supplier_name: "Delayed shop",
                description: "AI receipt",
                total: "12.34",
                currency: null,
              }
            : blankFields,
          provenance: {},
          parser_version: "fixture",
          warnings: [],
        },
      });
    }
    if (path === `/api/documents/${visionIds.pdf}/review`)
      return route.fulfill({
        json: {
          id: "legacy-review",
          document_id: visionIds.pdf,
          revision: 1,
          input_method: "text",
          status: "ready",
          error_code: null,
          document_type: "invoice",
          fields: {
            ...blankFields,
            supplier_name: "Legacy",
            description: "PDF",
            total: "1.00",
            currency: "PLN",
          },
          provenance: {},
          parser_version: "fixture",
          warnings: [],
        },
      });
    if (path === "/api/finance/accounts")
      return route.fulfill({
        json: [
          {
            id: "a1",
            name: "Synthetic account",
            type: "checking",
            currency: "PLN",
            is_active: true,
            is_budget_account: true,
            balance_pln: 0,
          },
        ],
      });
    if (path === "/api/finance/categories")
      return route.fulfill({
        json: [
          {
            id: "c1",
            name: "Synthetic category",
            type: "expense",
            is_active: true,
          },
        ],
      });
    if (path === "/api/documents/upload" && method === "POST") {
      uploadRequests.push({
        headers: request.headers(),
        body: request.postDataBuffer(),
      });
      const uploaded = document(
        visionIds.upload,
        "synthetic-upload.jpg",
        "image/jpeg",
        true,
      );
      if (!docs.some((entry) => entry.id === uploaded.id))
        docs.unshift(uploaded);
      return route.fulfill({
        json: { document: uploaded, is_duplicate: false },
      });
    }
    if (
      method === "POST" &&
      (path.endsWith("/vision/prepare") || path.endsWith("/retry-ocr"))
    ) {
      requests.push(`${method} ${path}`);
      expect(request.headerValue("Idempotency-Key")).toBeTruthy();
      if (path.endsWith("/vision/prepare") && options.visionRetryStatus === 429)
        return route.fulfill({
          status: 429,
          json: { detail: "vision_daily_limit" },
        });
      const documentId = path.split("/")[3];
      const doc = docs.find((item) => item.id === documentId)!;
      if (path.endsWith("/retry-ocr")) {
        doc.local_ocr_state = "pending";
        doc.local_ocr_job_id = `ocr-${documentId}`;
        return route.fulfill({
          status: 202,
          json: {
            id: documentId,
            status: "pending",
            job_id: doc.local_ocr_job_id,
          },
        });
      }
      return route.fulfill({
        status: 202,
        json: {
          id: reviewId(documentId),
          document_id: documentId,
          revision: 1,
          input_method: "image",
          status: "pending",
          error_code: null,
          document_type: "receipt",
          fields: blankFields,
          provenance: {},
          parser_version: "fixture",
          warnings: [],
        },
      });
    }
    return route.fallback();
  });
  return {
    requests,
    privateRequests,
    uploadRequests,
    assertClean: base.assertClean,
  };
}
