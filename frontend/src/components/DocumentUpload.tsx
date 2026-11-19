import { type ChangeEvent, type DragEvent, useRef, useState } from "react";
import { isAxiosError } from "axios";
import {
  formatFileSize,
  useDocumentUploadCapabilities,
  useUploadDocument,
  useRestoreDocument,
  documentArchiveError,
} from "../api/documents";
import {
  captureProcessingActor,
  isProcessingActorCurrent,
} from "../stores/documentProcessingStore";

import { DocumentIcon, DocumentTooltip } from "./documents/documentControls";

const ACCEPTED_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
];
type UploadItem = {
  id: number;
  file: File;
  state: "queued" | "uploading" | "success" | "error";
  error?: string;
  archivedDocumentId?: string;
  restored?: boolean;
};

function errorMessage(error: unknown) {
  const status = isAxiosError(error) ? error.response?.status : undefined;
  const data = isAxiosError(error) ? error.response?.data : undefined;
  const code =
    data &&
    typeof data === "object" &&
    "code" in data &&
    typeof data.code === "string"
      ? data.code
      : undefined;
  if (status === 400) {
    if (code === "document_mime_unsupported")
      return "Nieobsługiwany typ pliku. Wybierz PDF, JPG, PNG, HEIC lub HEIF.";
    if (code === "document_empty")
      return "Wybrany plik jest pusty. Wybierz go ponownie.";
    if (code === "document_validation_failed")
      return "Nie udało się odczytać pliku. Spróbuj wybrać oryginał przez Pliki zamiast biblioteki Zdjęć.";
    if (code === "document_mime_mismatch")
      return "Typ przesłanego pliku nie zgadza się z jego zawartością. Spróbuj wybrać oryginał przez Pliki zamiast biblioteki Zdjęć.";
  }
  if (status === 413)
    return "Przekroczono limit pliku lub miejsca na dokumenty.";
  if (status === 503 || status === 507)
    return "Przesyłanie jest chwilowo niedostępne. Spróbuj później.";
  return "Nie udało się przesłać dokumentu.";
}

export function DocumentUpload() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();
  const restore = useRestoreDocument();
  const capabilities = useDocumentUploadCapabilities();
  const [dragActive, setDragActive] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const nextId = useRef(0);
  const queue = useRef<UploadItem[]>([]);
  const draining = useRef(false);

  const drainQueue = async () => {
    if (draining.current) return;
    draining.current = true;
    while (queue.current.length) {
      const item = queue.current.shift()!;
      setItems((current) =>
        current.map((entry) =>
          entry.id === item.id ? { ...entry, state: "uploading" } : entry,
        ),
      );
      try {
        const actor = captureProcessingActor();
        const result = await upload.mutateAsync(item.file);
        if (!isProcessingActorCurrent(actor)) {
          queue.current = [];
          draining.current = false;
          return;
        }
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id
              ? {
                  ...entry,
                  state: "success",
                  archivedDocumentId: result.document.archived_at
                    ? result.document.id
                    : undefined,
                }
              : entry,
          ),
        );
      } catch (error) {
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id
              ? { ...entry, state: "error", error: errorMessage(error) }
              : entry,
          ),
        );
      }
    }
    draining.current = false;
  };
  const addFiles = (files: FileList | File[]) => {
    setValidationError(null);
    const valid = Array.from(files).filter(
      (file) =>
        file.size > 0 &&
        (file.type === "" ||
          file.type === "application/octet-stream" ||
          ACCEPTED_TYPES.includes(file.type)),
    );
    if (!valid.length) {
      setValidationError(
        "Wybierz niepusty plik PDF, JPG, PNG, HEIC lub HEIF. CSV nie jest dokumentem do sprawdzenia.",
      );
      return;
    }
    const newItems = valid.map((file) => ({
      id: nextId.current++,
      file,
      state: "queued" as const,
    }));
    setItems((current) => [...current, ...newItems]);
    queue.current.push(...newItems);
    void drainQueue();
  };
  const retry = (item: UploadItem) => {
    const queued = { ...item, state: "queued" as const, error: undefined };
    setItems((current) =>
      current.map((entry) => (entry.id === item.id ? queued : entry)),
    );
    queue.current.push(queued);
    void drainQueue();
  };
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = "";
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragActive(false);
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
  };
  const limit = capabilities.data
    ? `do ${formatFileSize(capabilities.data.max_file_bytes)}`
    : "zgodnie z limitem konta";

  return (
    <div className="mb-5">
      <p
        id="upload-privacy"
        className="mb-2 text-xs leading-relaxed text-gray-400"
      >
        {capabilities.data?.automatic_image_vision ? (
          <span role="status">
            Zdjęcia automatycznie trafiają do{" "}
            {capabilities.data.vision_provider_label ?? "dostawcy"} do odczytu
            AI.{" "}
          </span>
        ) : null}
        Odczyt AI może przekazać dostawcy treść pliku oraz nazwy i ścieżki
        Twoich kategorii wydatków. Szkic wymaga Twojego zatwierdzenia i sam nie
        tworzy płatności ani transakcji.
      </p>
      <div
        className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-dashed px-3 py-2.5 ${dragActive ? "border-advisor-400 bg-advisor-400/10" : "border-gray-700 bg-gray-900"}`}
        onDragOver={(event) => {
          if (!event.dataTransfer.types.includes("Files")) return;
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={(event) => {
          if (
            !(event.relatedTarget instanceof Node) ||
            !event.currentTarget.contains(event.relatedTarget)
          ) {
            setDragActive(false);
          }
        }}
        onDrop={onDrop}
      >
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-describedby="upload-formats upload-privacy"
            className="btn-primary inline-flex min-h-11 items-center gap-2"
            onClick={() => fileInputRef.current?.click()}
          >
            <DocumentIcon name="upload" />
            Dodaj dokument
          </button>
          <DocumentTooltip label="Aparat">
            <button
              type="button"
              aria-label="Aparat"
              aria-describedby="upload-privacy"
              className="document-icon-control"
              onClick={() => cameraInputRef.current?.click()}
            >
              <DocumentIcon name="camera" />
            </button>
          </DocumentTooltip>
        </div>
        <span id="upload-formats" className="text-xs text-gray-400">
          PDF, JPG, PNG, HEIC, HEIF · {limit}
        </span>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.jpg,.jpeg,.png,.heic,.heif,application/pdf,image/jpeg,image/png,image/heic,image/heif"
        className="hidden"
        onChange={onChange}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/jpeg,image/png,image/heic,image/heif,.jpg,.jpeg,.png,.heic,.heif"
        capture="environment"
        className="hidden"
        onChange={onChange}
      />
      {validationError && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {validationError}
        </p>
      )}
      {upload.isSuccess && items.length === 0 && (
        <p role="status" className="mt-2 text-sm text-green-300">
          {upload.data?.is_duplicate
            ? "Ten dokument jest już zapisany."
            : "Dokument przesłany. Stan odczytu sprawdzisz na liście."}
        </p>
      )}
      {items.length > 0 && (
        <ul className="mt-3 space-y-2" aria-label="Stan przesyłania">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-center gap-2 rounded-lg bg-gray-900 p-3 text-sm"
            >
              <span className="min-w-0 flex-1 truncate text-gray-200">
                {item.file.name}
              </span>
              <span role="status" className="text-gray-400">
                {item.archivedDocumentId
                  ? "Ten plik jest już w archiwum. Możesz go przywrócić."
                  : item.restored
                    ? "Dokument przywrócony."
                    : item.state === "uploading"
                      ? "Przesyłanie…"
                      : item.state === "queued"
                        ? "Oczekuje"
                        : item.state === "success"
                          ? "Przesłano"
                          : "Błąd"}
              </span>
              {item.archivedDocumentId && (
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={restore.isPending}
                  onClick={() =>
                    restore.mutate(
                      { documentId: item.archivedDocumentId! },
                      {
                        onSuccess: (_data, _variables, actor) => {
                          if (!isProcessingActorCurrent(actor)) return;
                          setItems((current) =>
                            current.map((entry) =>
                              entry.id === item.id
                                ? {
                                    ...entry,
                                    archivedDocumentId: undefined,
                                    restored: true,
                                  }
                                : entry,
                            ),
                          );
                        },
                      },
                    )
                  }
                >
                  Przywróć
                </button>
              )}
              {item.state === "error" && (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => retry(item)}
                >
                  Ponów
                </button>
              )}
              {item.error && (
                <span role="alert" className="text-red-300">
                  {item.error}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {restore.isError && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {documentArchiveError(restore.error)}
        </p>
      )}
    </div>
  );
}
