import type { DocumentData, DocumentReview } from "../api/documents";

export function processingDocument(
  overrides: Partial<DocumentData> = {},
): DocumentData {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    user_id: "owner",
    filename: "synthetic.jpg",
    original_name: "synthetic.jpg",
    mime_type: "image/jpeg",
    sha256_hash: "synthetic",
    size_bytes: 1,
    status: "done",
    attempt_count: 0,
    next_attempt_at: null,
    last_error_code: null,
    created_at: "2026-11-03T00:00:00Z",
    updated_at: "2026-11-03T00:00:00Z",
    processing_method: "vision",
    has_extracted_text: false,
    local_ocr_state: null,
    review: {
      revision_id: "revision-1",
      revision: 1,
      input_method: "image",
      status: "processing",
      error_code: null,
      warnings: [],
      job_state: "processing",
      job_id: "vision-job-1",
    },
    ...overrides,
  };
}

export function processingReview(
  overrides: Partial<DocumentReview> = {},
): DocumentReview {
  return {
    id: "revision-1",
    document_id: "11111111-1111-4111-8111-111111111111",
    revision: 1,
    status: "pending",
    error_code: null,
    document_type: "receipt",
    input_method: "image",
    warnings: [],
    provenance: { source: "vision" },
    parser_version: null,
    fields: {
      supplier_name: "Synthetic",
      supplier_tax_id: null,
      number: null,
      issue_date: null,
      sale_date: null,
      due_date: null,
      description: null,
      payee_iban: null,
      total: "1.00",
      currency: "PLN",
    },
    ...overrides,
  };
}
