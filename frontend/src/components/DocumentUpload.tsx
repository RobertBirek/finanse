import { type ChangeEvent, type DragEvent, useRef, useState } from "react";
import { isAxiosError } from "axios";
import {
  formatFileSize,
  useDocumentUploadCapabilities,
  useUploadDocument,
} from "../api/documents";

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
};

function errorMessage(error: unknown) {
  const status = isAxiosError(error) ? error.response?.status : undefined;
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
  const capabilities = useDocumentUploadCapabilities();
  const [dragActive, setDragActive] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const nextId = useRef(0);

  const runSequentially = async (newItems: UploadItem[]) => {
    for (const item of newItems) {
      setItems((current) =>
        current.map((entry) =>
          entry.id === item.id ? { ...entry, state: "uploading" } : entry,
        ),
      );
      try {
        await upload.mutateAsync(item.file);
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id ? { ...entry, state: "success" } : entry,
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
    void runSequentially(newItems);
  };
  const retry = (item: UploadItem) =>
    void runSequentially([{ ...item, state: "queued", error: undefined }]);
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = "";
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragActive(false);
    addFiles(event.dataTransfer.files);
  };
  const limit = capabilities.data
    ? `do ${formatFileSize(capabilities.data.max_file_bytes)}`
    : "zgodnie z limitem konta";

  return (
    <div className="mb-6">
      <button
        type="button"
        aria-label="Wybierz dokument do przesłania"
        aria-describedby="upload-formats"
        className={`w-full border-2 border-dashed rounded-xl p-8 text-center transition-colors ${dragActive ? "border-advisor-400 bg-advisor-400/10" : "border-gray-700 hover:border-gray-500 bg-gray-900"}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <span className="block text-gray-300 font-medium">
          Upuść dokumenty tutaj lub kliknij, aby wybrać
        </span>
        <span id="upload-formats" className="block text-gray-400 text-sm mt-1">
          PDF, JPG, PNG, HEIC, HEIF — {limit}
        </span>
      </button>
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
      <div className="flex gap-3 mt-3">
        <button
          type="button"
          onClick={() => cameraInputRef.current?.click()}
          className="min-h-11 flex-1 py-2 px-4 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-sm"
        >
          Aparat
        </button>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="min-h-11 flex-1 py-2 px-4 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-sm"
        >
          Galeria lub pliki
        </button>
      </div>
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
              className="flex items-center gap-2 rounded-lg bg-gray-900 p-3 text-sm"
            >
              <span className="min-w-0 flex-1 truncate text-gray-200">
                {item.file.name}
              </span>
              <span role="status" className="text-gray-400">
                {item.state === "uploading"
                  ? "Przesyłanie…"
                  : item.state === "queued"
                    ? "Oczekuje"
                    : item.state === "success"
                      ? "Przesłano"
                      : "Błąd"}
              </span>
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
    </div>
  );
}
