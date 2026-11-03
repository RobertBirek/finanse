import { useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import {
  useDocumentProcessingStore,
  type ProcessingActor,
  type ProcessingWatch,
} from "../../stores/documentProcessingStore";

export function ProcessingPulse() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3 w-3 shrink-0 rounded-full border-2 border-current border-r-transparent motion-safe:animate-spin"
    />
  );
}

function subscribeModalTarget(listener: () => void) {
  const observer = new MutationObserver(listener);
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["open"],
  });
  return () => observer.disconnect();
}
function modalTarget(): HTMLElement {
  const dialogs = document.querySelectorAll<HTMLDialogElement>("dialog[open]");
  return dialogs[dialogs.length - 1] ?? document.body;
}

export function ProcessingFeedback({
  actor,
  watches,
  hasError,
}: {
  actor: ProcessingActor;
  watches: ProcessingWatch[];
  hasError: boolean;
}) {
  const ownerId = useDocumentProcessingStore((s) => s.ownerId);
  const generation = useDocumentProcessingStore((s) => s.generation);
  const toasts = useDocumentProcessingStore((s) => s.toasts);
  const dismiss = useDocumentProcessingStore((s) => s.dismiss);
  const toastTarget = useSyncExternalStore(subscribeModalTarget, modalTarget);
  if (
    !actor.ownerId ||
    actor.ownerId !== ownerId ||
    actor.generation !== generation
  )
    return null;
  const labels: string[] = [];
  for (const kind of ["ai", "ocr"] as const) {
    for (const state of ["processing", "pending"]) {
      const count = watches.filter(
        (w) => w.kind === kind && w.state === state,
      ).length;
      if (count)
        labels.push(
          `${kind === "ai" ? "AI" : "OCR"} ${state === "pending" ? "w kolejce" : "pracuje"}${count > 1 ? ` (${count})` : ""}`,
        );
    }
  }
  const unknown = hasError || watches.some((w) => w.state === "unknown");
  return (
    <>
      {(watches.length > 0 || hasError) && (
        <div
          role="status"
          aria-label="Przetwarzanie dokumentów"
          className="flex shrink-0 flex-wrap items-center gap-2 border-b border-gray-800 bg-gray-900 px-4 py-2 text-xs text-gray-300 lg:px-6"
        >
          {!unknown && <ProcessingPulse />}
          <span>
            {unknown
              ? "Status odczytu chwilowo niedostępny — sprawdzamy ponownie."
              : labels.join(" · ")}
          </span>
        </div>
      )}
      {toasts.length > 0 &&
        createPortal(
          <section
            aria-label="Powiadomienia o odczycie"
            className="fixed bottom-24 left-3 right-3 z-[70] max-h-[50dvh] space-y-2 overflow-y-auto sm:left-auto sm:w-96 lg:bottom-6 lg:right-6"
          >
            {toasts.map((toast) => (
              <div
                key={toast.id}
                role={toast.tone === "error" ? "alert" : "status"}
                className="rounded-lg border border-l-4 p-4 text-sm shadow-xl"
                style={{
                  backgroundColor: "var(--ui-surface)",
                  color: "var(--ui-ink)",
                  borderColor: "var(--ui-line)",
                  borderLeftColor:
                    toast.tone === "error"
                      ? "var(--ui-red)"
                      : toast.tone === "warning"
                        ? "#b58105"
                        : "var(--ui-green)",
                }}
              >
                <div className="flex items-start gap-3">
                  <p className="min-w-0 flex-1">{toast.message}</p>
                  <button
                    type="button"
                    aria-label="Zamknij powiadomienie"
                    className="-mr-1 -mt-1 min-h-9 min-w-9 rounded hover:bg-[var(--ui-hover)] focus-visible:outline focus-visible:outline-2"
                    style={{ color: "var(--ui-muted)" }}
                    onClick={() => dismiss(toast.id)}
                  >
                    ×
                  </button>
                </div>
                <Link
                  to={`/documents?review=${encodeURIComponent(toast.documentId)}`}
                  className="mt-2 inline-flex min-h-9 items-center rounded text-advisor-300 underline underline-offset-4 focus-visible:outline focus-visible:outline-2"
                  style={{ color: "var(--ui-blue)" }}
                >
                  Otwórz dokument
                </Link>
              </div>
            ))}
          </section>,
          toastTarget,
        )}
    </>
  );
}
