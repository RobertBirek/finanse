import type { DocumentData } from "../../api/documents";

export type DocumentStatusTone = "neutral" | "warning" | "success" | "danger";

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
    if (review.status === "incomplete")
      return { label: "Uzupełnij ręcznie", tone: "warning" };
    return {
      label:
        review.error_code === "daily_limit_reached"
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
