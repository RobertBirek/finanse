import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  importError,
  useCreateImport,
  useUploadImportSource,
  usePrepareImportSource,
  useAttachImportDocument,
  type ImportKind,
} from "../../../api/bankImports";
import {
  captureProcessingActor,
  isProcessingActorCurrent,
} from "../../../stores/documentProcessingStore";

interface FileOutcome {
  name: string;
  message: string;
  batchId?: string;
  duplicate?: boolean;
}
export function ImportUpload({
  batchId,
  documentId,
  disabled = false,
  kind = "statement",
}: {
  batchId?: string;
  documentId?: string | null;
  disabled?: boolean;
  kind?: ImportKind;
}) {
  const create = useCreateImport();
  const [params] = useSearchParams();
  const upload = useUploadImportSource();
  const prepare = usePrepareImportSource();
  const attach = useAttachImportDocument();
  const [files, setFiles] = useState<File[]>([]);
  const [outcomes, setOutcomes] = useState<FileOutcome[]>([]);
  const [busy, setBusy] = useState(false);
  async function submit() {
    const actor = captureProcessingActor();
    if (!actor.ownerId || busy || disabled) return;
    setBusy(true);
    setOutcomes([]);
    try {
      const id =
        batchId ??
        (
          await create.mutateAsync({
            kind,
            idempotencyKey: crypto.randomUUID(),
          })
        ).id;
      if (!isProcessingActorCurrent(actor)) return;
      const inputs = documentId ? [null] : files;
      for (const file of inputs) {
        if (!isProcessingActorCurrent(actor)) return;
        const name = file?.name ?? "Wybrany dokument";
        try {
          const result = file
            ? await upload.mutateAsync({
                batchId: id,
                file,
                idempotencyKey: crypto.randomUUID(),
              })
            : await attach.mutateAsync({
                batchId: id,
                documentId: documentId!,
                idempotencyKey: crypto.randomUUID(),
              });
          if (!isProcessingActorCurrent(actor)) return;
          if (!result.is_duplicate)
            await prepare.mutateAsync({
              batchId: id,
              sourceId: result.source.id,
              idempotencyKey: crypto.randomUUID(),
            });
          if (!isProcessingActorCurrent(actor)) return;
          setOutcomes((current) => [
            ...current,
            {
              name,
              message: result.is_duplicate
                ? "To źródło już istnieje"
                : "Wymaga sprawdzenia",
              batchId: result.existing_batch_id ?? id,
              duplicate: result.is_duplicate,
            },
          ]);
        } catch (error) {
          if (!isProcessingActorCurrent(actor)) return;
          setOutcomes((current) => [
            ...current,
            { name, message: importError(error) },
          ]);
        }
      }
    } catch (error) {
      if (isProcessingActorCurrent(actor))
        setOutcomes([{ name: "Import", message: importError(error) }]);
    } finally {
      if (isProcessingActorCurrent(actor)) setBusy(false);
    }
  }
  return (
    <section className="card space-y-4" aria-label="Dodawanie wyciągów">
      <div>
        <h2 className="text-xl">Dodaj źródła</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {kind === "loan_schedule"
            ? "Harmonogram Velo: tekstowy PDF PLN. Bez skanów, OCR i AI. Dodanie pliku nie aktywuje planu ani nie księguje spłat."
            : "Velo i ING Direct: tekstowy PDF. Revolut: CSV PLN, EUR lub USD. Bez skanów, OCR i AI. Dodanie pliku nie księguje operacji."}
        </p>
      </div>
      {documentId ? (
        <p>Wybrany dokument: {documentId}</p>
      ) : (
        <label className="block text-sm">
          {kind === "loan_schedule" ? "Pliki harmonogramów" : "Pliki wyciągów"}
          <input
            className="input mt-2 block w-full"
            type="file"
            multiple
            accept={kind === "loan_schedule" ? ".pdf" : ".pdf,.csv"}
            aria-label={
              kind === "loan_schedule"
                ? "Pliki harmonogramów"
                : "Pliki wyciągów"
            }
            disabled={busy || disabled}
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </label>
      )}
      <button
        type="button"
        className="btn-primary"
        disabled={disabled || busy || (!documentId && files.length === 0)}
        onClick={submit}
      >
        {busy
          ? "Zapisywanie źródeł…"
          : documentId
            ? "Dodaj dokument do importu"
            : "Dodaj pliki"}
      </button>
      <ul aria-live="polite" className="space-y-2">
        {outcomes.map((result, index) => (
          <li key={index} className="break-words text-sm">
            <span>
              {result.name} — {result.message}
            </span>
            {result.batchId ? (
              <Link
                className="ml-2 underline"
                to={`/finances/imports/${encodeURIComponent(result.batchId)}${params.get("loan") ? `?loan=${encodeURIComponent(params.get("loan")!)}` : params.get("account") ? `?account=${encodeURIComponent(params.get("account")!)}` : ""}`}
              >
                {result.duplicate
                  ? "Otwórz istniejący import"
                  : "Sprawdź import"}
              </Link>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
