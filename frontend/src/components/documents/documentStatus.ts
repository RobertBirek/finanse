import type { DocumentData } from "../../api/documents";

export type DocumentStatusTone = "neutral" | "warning" | "success" | "danger";

const limitErrors = new Set(["daily_limit_reached", "vision_daily_limit"]);
const unavailableErrors = new Set([
  "configuration_missing",
  "vision_disabled",
  "vision_configuration_changed",
  "vision_failed",
  "invalid_model_output",
  "processing_failed",
  "attempts_exhausted",
]);

export function getDocumentStatus(
  document: Pick<DocumentData, "status" | "review">,
): { label: string; tone: DocumentStatusTone } {
  const review = document.review;
  if (review) {
    if (review.status === "pending")
      return { label: "Odczyt w kolejce", tone: "neutral" };
    if (review.status === "processing")
      return { label: "Odczytywanie", tone: "warning" };
    if (review.status === "ready")
      return { label: "Propozycja do sprawdzenia", tone: "success" };
    if (limitErrors.has(review.error_code ?? ""))
      return { label: "Limit odczytów AI", tone: "danger" };
    if (unavailableErrors.has(review.error_code ?? ""))
      return { label: "AI niedostępne", tone: "danger" };
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
