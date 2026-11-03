import type { DocumentReview } from "../../api/documents";
import { useAuthStore } from "../../stores/authStore";
import { useDocumentProcessingStore } from "../../stores/documentProcessingStore";
import { ProcessingPulse } from "./ProcessingFeedback";

export function DocumentProcessingInline({
  documentId,
  review,
}: {
  documentId: string;
  review?: DocumentReview;
}) {
  const owner = useAuthStore((s) => s.user?.id);
  const state = useDocumentProcessingStore();
  const watches =
    state.ownerId === owner
      ? Object.values(state.watches).filter((w) => w.documentId === documentId)
      : [];
  const labels = watches.map(
    (w) =>
      `${w.kind === "ai" ? "AI" : "OCR"} ${w.state === "pending" ? "w kolejce" : "pracuje"}`,
  );
  if (
    !watches.some((w) => w.kind === "ai") &&
    review &&
    (review.status === "pending" || review.status === "processing") &&
    !state.seen[`review:${review.id}`]
  )
    labels.push(review.status === "pending" ? "AI w kolejce" : "AI pracuje");
  if (!labels.length) return null;
  const unknown = watches.some((w) => w.state === "unknown");
  return (
    <p
      role="status"
      aria-label="Odczyt dokumentu"
      className="mb-3 flex items-center gap-2 text-sm text-gray-300"
    >
      {!unknown && <ProcessingPulse />}
      <span>
        {unknown
          ? "Status odczytu chwilowo niedostępny — sprawdzamy ponownie."
          : [...new Set(labels)].join(" · ")}
      </span>
    </p>
  );
}
