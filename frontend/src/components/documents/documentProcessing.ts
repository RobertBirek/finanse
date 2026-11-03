import type { DocumentData } from "../../api/documents";

export type ProcessingOperation = {
  id: string;
  documentId: string;
  kind: "ai" | "ocr";
  source: "review" | "local_ocr" | "legacy_ocr";
  state: string;
  reviewStatus?: string;
  warnings?: string[];
  errorCode?: string | null;
};
export type ProcessingNotice = {
  tone: "success" | "warning" | "error";
  message: string;
};

export function getDocumentOperations(
  document: DocumentData,
): ProcessingOperation[] {
  const operations: ProcessingOperation[] = [];
  const review = document.review;
  if (review) {
    operations.push({
      id: `review:${review.revision_id}`,
      documentId: document.id,
      source: "review",
      kind: "ai",
      state:
        review.job_state ??
        (review.status === "pending" || review.status === "processing"
          ? review.status
          : review.error_code || review.status === "error"
            ? "failed"
            : "succeeded"),
      reviewStatus: review.status,
      warnings: review.warnings,
      errorCode: review.error_code,
    });
  } else if (
    document.processing_method === "vision" &&
    (document.status === "pending" || document.status === "processing")
  ) {
    operations.push({
      id: `upload:${document.id}`,
      documentId: document.id,
      source: "review",
      kind: "ai",
      state: document.status,
    });
  }
  if (document.local_ocr_state) {
    operations.push({
      id: `ocr:${document.local_ocr_job_id ?? document.id}`,
      documentId: document.id,
      source: "local_ocr",
      kind: "ocr",
      state: document.local_ocr_state,
      errorCode: document.local_ocr_error_code,
    });
  }
  if (document.processing_method === "legacy_ocr") {
    operations.push({
      id: `legacy:${document.id}`,
      documentId: document.id,
      source: "legacy_ocr",
      kind: "ocr",
      state:
        document.status === "done"
          ? "succeeded"
          : document.status === "error"
            ? "failed"
            : document.status,
      errorCode: document.last_error_code,
    });
  }
  return operations;
}
export function isActiveOperation(operation: ProcessingOperation): boolean {
  return operation.state === "pending" || operation.state === "processing";
}
export function getOperationNotice(
  operation: ProcessingOperation,
): ProcessingNotice | null {
  const label = operation.kind === "ai" ? "AI" : "OCR";
  if (operation.state === "paused")
    return {
      tone: "warning",
      message: `Odczyt ${label} wstrzymany — sprawdź dokument.`,
    };
  if (operation.state === "failed")
    return {
      tone: "error",
      message: `Odczyt ${label} nie powiódł się — sprawdź dokument.`,
    };
  if (operation.state !== "succeeded") return null;
  if (
    operation.kind === "ai" &&
    (operation.reviewStatus !== "ready" || operation.warnings?.length)
  ) {
    return {
      tone: "warning",
      message: "AI zakończyło odczyt — sprawdź i uzupełnij dane.",
    };
  }
  return {
    tone: "success",
    message:
      operation.kind === "ai"
        ? "Propozycja z AI gotowa — sprawdź dane."
        : "OCR zakończony — sprawdź odczyt.",
  };
}
