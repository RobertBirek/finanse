import { useRef, useState, DragEvent, ChangeEvent } from "react";
import { useUploadDocument } from "../api/documents";
import { isAxiosError } from "axios";

export function DocumentUpload() {
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();
  const status = isAxiosError(upload.error)
    ? upload.error.response?.status
    : undefined;
  const uploadError =
    status === 413
      ? "Przekroczono limit pliku lub miejsca na dokumenty. Wybierz mniejszy plik lub sprawdź limit przechowywania."
      : status === 503 || status === 507
        ? "Przesyłanie jest chwilowo niedostępne. Spróbuj później."
        : "Nie udało się przesłać dokumentu. Wybierz plik ponownie, aby spróbować jeszcze raz.";

  const [validationError, setValidationError] = useState<string | null>(null);
  const handleFile = (file: File) => {
    if (upload.isPending) return;
    setValidationError(null);
    if (
      !/\.(pdf|jpe?g|png)$/i.test(file.name) ||
      file.size === 0 ||
      file.size > 20 * 1024 * 1024
    ) {
      setValidationError(
        "Wybierz niepusty plik PDF, JPG lub PNG o rozmiarze do 20 MB.",
      );
      return;
    }
    upload.mutate(file);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  return (
    <div className="mb-6">
      <button
        type="button"
        disabled={upload.isPending}
        aria-label="Wybierz dokument do przesłania"
        aria-describedby="upload-formats"
        className={`w-full border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
          dragActive
            ? "border-advisor-400 bg-advisor-400/10"
            : "border-gray-700 hover:border-gray-500 bg-gray-900"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <svg
          className="w-12 h-12 mx-auto mb-3 text-gray-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <span className="block text-gray-300 font-medium">
          Upuść dokument tutaj lub kliknij, aby wybrać
        </span>
        <span id="upload-formats" className="block text-gray-400 text-sm mt-1">
          PDF, JPG, PNG — max 20 MB
        </span>
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.jpg,.jpeg,.png"
        className="hidden"
        onChange={handleChange}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleChange}
      />
      <div className="flex gap-3 mt-3">
        <button
          type="button"
          disabled={upload.isPending}
          onClick={(e) => {
            e.stopPropagation();
            cameraInputRef.current?.click();
          }}
          className="flex-1 py-2 px-4 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-sm transition-colors flex items-center justify-center gap-2"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
          Aparat
        </button>
      </div>
      {upload.isPending && (
        <div
          role="status"
          className="mt-2 text-sm text-yellow-400 flex items-center gap-2"
        >
          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
              className="opacity-25"
            />
            <path
              fill="currentColor"
              className="opacity-75"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          Przesyłanie...
        </div>
      )}
      {validationError && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {validationError}
        </p>
      )}
      {!validationError && upload.isError && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {uploadError}
        </p>
      )}
      {!validationError && upload.isSuccess && (
        <p role="status" className="mt-2 text-sm text-green-300">
          {upload.data?.is_duplicate
            ? "Ten dokument jest już zapisany."
            : "Dokument przesłany. Stan odczytu sprawdzisz na liście."}
        </p>
      )}
    </div>
  );
}
