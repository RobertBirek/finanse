import { useEffect, useRef, useState } from "react";
import { Dialog } from "../Dialog";
import { DocumentIcon } from "./documentControls";
import {
  cameraAccept,
  invalidPhotoMessage,
  isCameraPhoto,
} from "./cameraFiles";

function PhotoPreview({ file }: { file: File }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setFailed(false);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  if (failed)
    return (
      <p className="p-4 text-center text-sm text-gray-400">
        Ta przeglądarka nie wyświetla podglądu tego formatu. Możesz powtórzyć
        ujęcie albo wysłać zdjęcie.
      </p>
    );
  return previewUrl ? (
    <img
      src={previewUrl}
      alt="Podgląd zdjęcia dokumentu"
      onError={() => setFailed(true)}
      className="mx-auto max-h-[55vh] w-full object-contain"
    />
  ) : null;
}

export function CameraScanDialog({
  firstPhoto,
  maxPages,
  maxBytes,
  onClose,
  onSend,
}: {
  firstPhoto: File;
  maxPages: number;
  maxBytes?: number;
  onClose: () => void;
  onSend: (files: File[]) => void;
}) {
  const [photos, setPhotos] = useState([firstPhoto]);
  const [selected, setSelected] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const mode = useRef<"add" | "retake">("add");
  const selectPhoto = (action: "add" | "retake") => {
    mode.current = action;
    input.current?.click();
  };
  const movePhoto = (offset: -1 | 1) => {
    const destination = selected + offset;
    const reordered = [...photos];
    [reordered[selected], reordered[destination]] = [
      reordered[destination],
      reordered[selected],
    ];
    setPhotos(reordered);
    setSelected(destination);
  };
  const currentPhoto = photos[selected];
  const exceedsLimit =
    maxBytes !== undefined &&
    photos.reduce((sum, file) => sum + file.size, 0) > maxBytes;
  return (
    <Dialog
      label="Podgląd skanu"
      onClose={onClose}
      panelClassName="card w-full max-w-xl min-w-0 space-y-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-white">Podgląd skanu</h2>
        <button
          type="button"
          aria-label="Zamknij podgląd skanu"
          className="document-icon-control"
          onClick={onClose}
        >
          <DocumentIcon name="close" />
        </button>
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-800 bg-gray-950">
        <PhotoPreview file={currentPhoto} />
      </div>
      {photos.length > 1 && (
        <div
          role="group"
          aria-label="Kolejność stron"
          className="flex flex-wrap gap-2"
        >
          {photos.map((file, index) => (
            <button
              key={index}
              type="button"
              title={file.name}
              aria-pressed={selected === index}
              className={
                selected === index
                  ? "btn-primary text-sm"
                  : "btn-secondary text-sm"
              }
              onClick={() => setSelected(index)}
            >
              Strona {index + 1}
            </button>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary text-sm"
          onClick={() => selectPhoto("retake")}
        >
          Powtórz zdjęcie
        </button>
        {maxPages > 1 && (
          <button
            type="button"
            className="btn-secondary text-sm disabled:opacity-50"
            disabled={photos.length >= maxPages}
            onClick={() => selectPhoto("add")}
          >
            Dodaj stronę
          </button>
        )}
        {photos.length > 1 && (
          <>
            <button
              type="button"
              className="btn-secondary text-sm disabled:opacity-50"
              disabled={selected === 0}
              onClick={() => movePhoto(-1)}
            >
              Przesuń wcześniej
            </button>
            <button
              type="button"
              className="btn-secondary text-sm disabled:opacity-50"
              disabled={selected === photos.length - 1}
              onClick={() => movePhoto(1)}
            >
              Przesuń później
            </button>
            <button
              type="button"
              className="btn-secondary text-sm"
              onClick={() => {
                setPhotos(photos.filter((_, index) => index !== selected));
                setSelected(Math.min(selected, photos.length - 2));
                setError(null);
              }}
            >
              Usuń stronę
            </button>
          </>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept={cameraAccept}
        capture="environment"
        className="hidden"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (!file) return;
          if (!isCameraPhoto(file)) {
            setError(invalidPhotoMessage);
            return;
          }
          const next =
            mode.current === "retake"
              ? photos.map((photo, index) =>
                  index === selected ? file : photo,
                )
              : [...photos, file];
          if (
            next.length > maxPages ||
            (maxBytes !== undefined &&
              next.reduce((sum, photo) => sum + photo.size, 0) > maxBytes)
          ) {
            setError(
              "Skan przekracza limit stron lub rozmiaru. Wybierz mniejsze zdjęcie.",
            );
            return;
          }
          if (mode.current === "add") setSelected(photos.length);
          setPhotos(next);
          setError(null);
        }}
      />
      {(error || exceedsLimit) && (
        <p role="alert" className="text-sm text-red-300">
          {error ??
            "Zdjęcie przekracza limit rozmiaru. Wybierz mniejsze zdjęcie."}
        </p>
      )}
      <button
        type="button"
        className="btn-primary"
        disabled={exceedsLimit || photos.length > maxPages}
        onClick={() => onSend(photos)}
      >
        {photos.length > 1 ? "Wyślij jako PDF" : "Wyślij zdjęcie"}
      </button>
    </Dialog>
  );
}
