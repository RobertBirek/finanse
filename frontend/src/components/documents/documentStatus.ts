import type { DocumentData } from "../../api/documents";

export type DocumentStatusTone = "neutral" | "warning" | "success" | "danger";

const limitErrors = new Set(["daily_limit_reached", "vision_daily_limit"]);
const unavailableErrors = new Set([
  "configuration_missing",
  "vision_disabled",
  "vision_configuration_changed",
  "vision_failed",
  "provider_auth_failed",
  "provider_response_too_large",
  "provider_timeout",
  "provider_unavailable",
  "processing_failed",
]);

export function getDocumentStatus(
  document: Pick<DocumentData, "status" | "review"> &
    Partial<Pick<DocumentData, "local_ocr_state" | "processing_method">>,
): { label: string; tone: DocumentStatusTone } {
  if (document.local_ocr_state === "pending")
    return { label: "OCR w kolejce", tone: "neutral" };
  if (document.local_ocr_state === "processing")
    return { label: "OCR pracuje", tone: "warning" };
  const review = document.review;
  if (
    review?.job_state &&
    ![
      "pending",
      "processing",
      "succeeded",
      "failed",
      "paused",
      "superseded",
    ].includes(review.job_state)
  )
    return { label: "Status odczytu nieznany", tone: "warning" };
  if (review?.job_state === "pending")
    return { label: "AI w kolejce", tone: "neutral" };
  if (review?.job_state === "processing")
    return { label: "AI pracuje", tone: "warning" };
  if (review?.job_state === "paused")
    return { label: "Odczyt AI wstrzymany", tone: "neutral" };
  if (review?.job_state === "superseded")
    return { label: "Odczyt zastąpiony", tone: "neutral" };
  if (document.processing_method === "legacy_ocr") {
    if (document.status === "pending")
      return { label: "OCR w kolejce", tone: "neutral" };
    if (document.status === "processing")
      return { label: "OCR pracuje", tone: "warning" };
  }
  if (review) {
    const terminalJob =
      review.job_state === "succeeded" || review.job_state === "failed";
    if (!terminalJob && review.status === "pending")
      return { label: "AI w kolejce", tone: "neutral" };
    if (!terminalJob && review.status === "processing")
      return { label: "AI pracuje", tone: "warning" };
    if (review.status === "ready" && review.job_state !== "failed")
      return { label: "Propozycja do sprawdzenia", tone: "success" };
    if (review.error_code === "invalid_model_output")
      return { label: "Nieprawidłowy wynik AI", tone: "warning" };
    if (review.error_code === "attempts_exhausted")
      return { label: "Odczyt AI przerwany", tone: "warning" };
    if (limitErrors.has(review.error_code ?? ""))
      return { label: "Limit odczytów AI", tone: "danger" };
    if (unavailableErrors.has(review.error_code ?? ""))
      return { label: "AI niedostępne", tone: "danger" };
    if (review.job_state === "failed")
      return { label: "Odczyt AI przerwany", tone: "warning" };
    if (review.status === "incomplete")
      return { label: "Uzupełnij ręcznie", tone: "warning" };
    return {
      label: limitErrors.has(review.error_code ?? "")
        ? "Limit odczytów AI"
        : "AI niedostępne",
      tone: "danger",
    };
  }
  if (document.status === "done")
    return { label: "OCR zakończony — sprawdź dane", tone: "success" };
  if (document.status === "error") return { label: "Błąd", tone: "danger" };
  return {
    label: document.status === "processing" ? "Przetwarzanie" : "Oczekuje",
    tone: "warning",
  };
}
