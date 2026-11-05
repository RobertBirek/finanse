import { useRef, useState, useLayoutEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import { useAuthStore } from "../../../stores/authStore";
import {
  useReceiptReadContext,
  useReceiptReadHistory,
  useReceiptReadJob,
  useReceiptReadResult,
  usePreviewReceiptReadExport,
  useStartReceiptRead,
  useCancelReceiptRead,
  usePreviewReceiptReadImport,
  useImportReceiptRead,
  fetchReceiptReadJob,
} from "../../../api/receiptRead";
import type {
  ReceiptReadExportPreview,
  ReceiptReadImportPreview,
  ReceiptReadState,
} from "../../../api/receiptRead";
import { ReceiptReadConsent } from "./ReceiptReadConsent";
import { ReceiptReadResult } from "./ReceiptReadResult";
import {
  loadReceiptReadIntent,
  persistReceiptReadIntent,
  clearReceiptReadIntent,
} from "./receiptReadIntent";
import type { ReceiptReadIntent } from "./receiptReadIntent";

const labels: Record<ReceiptReadState, string> = {
  pending: "Oczekuje na odczyt",
  preparing: "Przygotowanie zdjęcia",
  dispatched: "Odczyt w toku — wysyłka rozpoczęta",
  succeeded: "Wynik gotowy do przejrzenia",
  failed: "Nie udało się odczytać",
  unknown: "Wynik wysłania nieznany — próba mogła być płatna",
  paused: "Odczyt wstrzymany",
  cancelled: "Anulowano przed wysyłką",
  superseded: "Próba nieaktualna — wynik nie zostanie przyjęty",
};
type Intent = ReceiptReadIntent;
export function ReceiptReadPanel({
  billId,
  dirty,
  disabled,
  onImported,
  onImportLockChange,
}: {
  billId: string;
  dirty: boolean;
  disabled: boolean;
  onImported: () => Promise<void>;
  onImportLockChange: (locked: boolean) => void;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const [owner] = useState(() => useAuthStore.getState().user?.id ?? null);
  const [recovered] = useState(() =>
    loadReceiptReadIntent(owner, billId, session),
  );
  const client = useQueryClient();
  const importNotify = useRef(onImportLockChange);
  importNotify.current = onImportLockChange;
  useLayoutEffect(() => {
    if (recovered?.intent.action === "import") importNotify.current(true);
  }, [recovered]);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const [sourceCursor, setSourceCursor] = useState<string | null>(null),
    [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const context = useReceiptReadContext(billId, sourceCursor),
    history = useReceiptReadHistory(billId, historyCursor);
  const [photo, setPhoto] = useState(recovered?.photo ?? ""),
    [jobId, setJobId] = useState<string | null>(recovered?.jobId ?? null);
  const job = useReceiptReadJob(billId, jobId),
    result = useReceiptReadResult(
      billId,
      job.data?.state === "succeeded" ? jobId : null,
    );
  const exportCommand = usePreviewReceiptReadExport(),
    startCommand = useStartReceiptRead(),
    cancelCommand = useCancelReceiptRead(),
    importPreviewCommand = usePreviewReceiptReadImport(),
    importCommand = useImportReceiptRead();
  const [consent, setConsent] = useState<ReceiptReadExportPreview | null>(null),
    [adoption, setAdoption] = useState<ReceiptReadImportPreview | null>(null);
  const [busy, setBusy] = useState(false),
    [uncertain, setUncertain] = useState(!!recovered),
    [message, setMessage] = useState<string | null>(null);
  const gate = useRef(false),
    generation = useRef(0),
    intent = useRef<Intent | null>(recovered?.intent ?? null);
  const current = () =>
    active && session === useAuthStore.getState().sessionVersion;
  const locked = disabled || !active || busy || uncertain || !!adoption;
  const selected = context.data?.sources?.find((s) => s.document_id === photo);
  const validConsent =
    !!consent &&
    context.data?.enabled &&
    consent.document_id === photo &&
    consent.source_sha256 === selected?.source_sha256 &&
    consent.provider === context.data.provider &&
    consent.model === context.data.model &&
    consent.policy_epoch === context.data.policy_epoch;
  function choose(value: string, id: string | null = null) {
    if (gate.current || uncertain || adoption) return;
    generation.current++;
    setPhoto(value);
    setJobId(id);
    setConsent(null);
    setMessage(null);
  }
  async function previewExport(reread: string | null = null) {
    if (gate.current || locked || !current() || !photo) return;
    gate.current = true;
    setBusy(true);
    setConsent(null);
    setMessage(null);
    const ticket = ++generation.current;
    try {
      const p = await exportCommand.mutateAsync({
        session,
        billId,
        body: { document_id: photo, reread_of_job_id: reread },
      });
      if (current() && ticket === generation.current) setConsent(p);
    } catch {
      if (current())
        setMessage(
          "Nie można przygotować wysyłki. Odśwież źródło i sprawdź, czy odczyt jest włączony.",
        );
    } finally {
      gate.current = false;
      if (current()) setBusy(false);
    }
  }
  async function run(action: Intent["action"]) {
    if (gate.current || !current() || disabled) return;
    let captured = intent.current;
    if (!captured) {
      let body: Record<string, unknown>;
      let id: string | undefined;
      if (action === "start") {
        if (!validConsent || !consent) return;
        body = {
          document_id: consent.document_id,
          reread_of_job_id: consent.reread_of_job_id,
          expected_export_snapshot: consent.export_snapshot,
          confirmed: true,
        };
      } else if (action === "cancel") {
        if (!job.data?.can_cancel) return;
        id = job.data.id;
        body = { expected_version: job.data.version };
      } else {
        if (!adoption) return;
        body = {
          job_id: adoption.job_id,
          expected_state_version: adoption.state_version,
          expected_import_snapshot: adoption.import_snapshot,
          confirmed_replace: true,
        };
      }
      captured = {
        action,
        input: {
          session,
          billId,
          key: crypto.randomUUID(),
          body,
          ...(id ? { jobId: id } : {}),
        },
      };
      intent.current = captured;
    }
    if (
      !persistReceiptReadIntent(owner, billId, session, captured, photo, jobId)
    ) {
      intent.current = null;
      setMessage(
        "Nie można zachować klucza operacji w tej przeglądarce. Nie wysłano polecenia; sprawdź dostępność pamięci karty.",
      );
      return;
    }
    gate.current = true;
    setBusy(true);
    setMessage(null);
    if (captured.action === "import") onImportLockChange(true);
    try {
      if (captured.action === "start") {
        const j = await startCommand.mutateAsync(captured.input);
        if (!current()) return;
        setJobId(j.id);
        await client.fetchQuery({
          queryKey: ["finance", "receipt-read", session, billId, "job", j.id],
          queryFn: ({ signal }) =>
            fetchReceiptReadJob(session, billId, j.id, signal),
          retry: false,
          staleTime: 0,
        });
        if (!current()) return;
        setConsent(null);
      } else if (captured.action === "cancel") {
        await cancelCommand.mutateAsync(captured.input);
        if (!current()) return;
        const canonical = await job.refetch();
        if (canonical.isError) throw new Error("receipt_read_reload_failed");
      } else {
        await importCommand.mutateAsync(captured.input);
        if (!current()) return;
        await onImported();
        if (!current()) return;
        setAdoption(null);
        onImportLockChange(false);
      }
      if (current()) {
        intent.current = null;
        clearReceiptReadIntent(owner, billId);
        setUncertain(false);
      }
    } catch (error) {
      if (current()) {
        const status = (error as AxiosError).response?.status;
        const unknown = !status || status >= 500;
        setUncertain(unknown);
        if (!unknown) {
          intent.current = null;
          clearReceiptReadIntent(owner, billId);
          setConsent(null);
          if (captured.action === "import") {
            setAdoption(null);
            onImportLockChange(false);
          }
          void context.refetch();
          if (jobId) void job.refetch();
        }
        setMessage(
          unknown
            ? "Wynik polecenia nieznany. Sprawdź tę samą próbę, bez nowej zgody i kolejnego wysyłania."
            : status === 409 && captured.action === "cancel"
              ? "Wysyłka mogła już się rozpocząć; nie można cofnąć przekazania zdjęcia. Sprawdź aktualny stan."
              : "Dane lub dostępność zmieniły się. Własne wpisy pozostały bez zmian; sprawdź aktualny stan.",
        );
      }
    } finally {
      gate.current = false;
      if (current()) setBusy(false);
    }
  }
  async function prepareImport() {
    if (gate.current || locked || !current() || !jobId || !context.data) return;
    gate.current = true;
    setBusy(true);
    onImportLockChange(true);
    setMessage(null);
    try {
      const p = await importPreviewCommand.mutateAsync({
        session,
        billId,
        body: {
          job_id: jobId,
          expected_state_version: context.data.state_version,
        },
      });
      if (current()) setAdoption(p);
    } catch {
      if (current()) {
        setMessage(
          "Nie można przenieść wyniku. Własne wpisy zostały zachowane. Sprawdź aktualny paragon i źródło.",
        );
        onImportLockChange(false);
        void context.refetch();
      }
    } finally {
      gate.current = false;
      if (current()) setBusy(false);
    }
  }
  const terminal =
    job.data &&
    !["pending", "preparing", "dispatched"].includes(job.data.state);
  return (
    <section
      aria-label="Odczyt produktów ze zdjęcia"
      className="space-y-3 rounded border border-gray-700 p-3 text-sm [overflow-wrap:anywhere]"
    >
      <h3 className="text-base font-semibold">Produkty ze zdjęcia</h3>
      <p>
        Odczyt nagłówka nie odczytuje produktów. Możesz nadal wpisywać je
        ręcznie.
      </p>
      {!active ? (
        <p role="alert">Sesja zmieniła się. Otwórz paragon ponownie.</p>
      ) : null}
      {context.isError ? (
        <p role="alert">
          Nie udało się pobrać źródeł odczytu.{" "}
          <button type="button" onClick={() => void context.refetch()}>
            Odśwież źródła
          </button>
        </p>
      ) : null}
      {context.data && !context.data.enabled ? (
        <p>
          {context.data.blocked_reason ??
            "Odczyt AI jest wyłączony. Edytor ręczny pozostaje dostępny."}
        </p>
      ) : null}
      <label className="block">
        Zdjęcie paragonu
        <select
          className="input mt-1 w-full"
          value={photo}
          disabled={locked}
          onChange={(e) => choose(e.target.value)}
        >
          <option value="">Wybierz jeden załącznik</option>
          {(context.data?.sources ?? []).map((s) => (
            <option
              key={s.document_id}
              value={s.document_id}
              disabled={!s.allowed}
            >
              {s.name} · {s.mime_type}
              {!s.allowed ? " — niedostępny" : ""}
            </option>
          ))}
        </select>
      </label>
      {context.data?.next_source_cursor ? (
        <button
          type="button"
          className="btn-secondary"
          disabled={locked}
          onClick={() => {
            choose("");
            setSourceCursor(context.data!.next_source_cursor);
          }}
        >
          Dalsze załączniki
        </button>
      ) : sourceCursor ? (
        <button
          type="button"
          className="btn-secondary"
          disabled={locked}
          onClick={() => {
            choose("");
            setSourceCursor(null);
          }}
        >
          Pierwsze załączniki
        </button>
      ) : null}
      {selected ? (
        <a
          className="inline-block underline"
          href={`/api/documents/${encodeURIComponent(selected.document_id)}/preview`}
          target="_blank"
          rel="noopener noreferrer"
        >
          Podejrzyj wybrane zdjęcie
        </a>
      ) : null}
      <button
        type="button"
        className="btn-secondary"
        disabled={locked || !selected?.allowed || !context.data?.enabled}
        onClick={() => void previewExport()}
      >
        Odczytaj produkty ze zdjęcia
      </button>
      {validConsent && consent && !uncertain ? (
        <ReceiptReadConsent
          preview={consent}
          disabled={busy || disabled || !active}
          onConfirm={() => void run("start")}
          onBack={() => setConsent(null)}
        />
      ) : null}
      {(history.data?.items ?? []).length ? (
        <div className="space-y-1">
          <h4 className="font-medium">Zapisane próby odczytu</h4>
          {history.data!.items.map((j) => (
            <button
              type="button"
              className="btn-secondary mr-2"
              key={j.id}
              disabled={locked}
              onClick={() => choose(j.document_id, j.id)}
            >
              Próba {j.generation} · {labels[j.state]}
            </button>
          ))}
        </div>
      ) : null}
      {history.isError ? (
        <p role="alert">
          Nie udało się pobrać historii.{" "}
          <button type="button" onClick={() => void history.refetch()}>
            Odśwież próby
          </button>
        </p>
      ) : null}
      {history.data?.next_cursor ? (
        <button
          type="button"
          className="btn-secondary"
          disabled={locked}
          onClick={() => setHistoryCursor(history.data!.next_cursor)}
        >
          Starsze próby
        </button>
      ) : historyCursor ? (
        <button
          type="button"
          className="btn-secondary"
          disabled={locked}
          onClick={() => setHistoryCursor(null)}
        >
          Najnowsze próby
        </button>
      ) : null}
      {job.data ? (
        <div className="space-y-2">
          <p role="status">{labels[job.data.state]}</p>
          <button
            type="button"
            className="btn-secondary"
            disabled={busy || !active}
            onClick={() => void job.refetch()}
          >
            Sprawdź wynik
          </button>
          {job.data.can_cancel ? (
            <button
              type="button"
              className="btn-secondary"
              disabled={locked}
              onClick={() => void run("cancel")}
            >
              Anuluj niewysłany odczyt
            </button>
          ) : null}
          {terminal ? (
            <button
              type="button"
              className="btn-secondary"
              disabled={locked || !context.data?.enabled || !selected?.allowed}
              onClick={() => void previewExport(job.data!.id)}
            >
              Odczytaj ponownie — możliwy kolejny koszt
            </button>
          ) : null}
        </div>
      ) : job.isError ? (
        <p role="alert">
          Nie udało się sprawdzić próby; nie wysłano nowego zdjęcia.
        </p>
      ) : null}
      {result.data && job.data?.state === "succeeded" ? (
        <ReceiptReadResult
          result={result.data}
          disabled={locked}
          onUse={() => void prepareImport()}
        />
      ) : result.isError && job.data?.state === "succeeded" ? (
        <p role="alert">
          Nie udało się pobrać wyniku.{" "}
          <button type="button" onClick={() => void result.refetch()}>
            Pobierz wynik ponownie
          </button>
        </p>
      ) : null}
      {adoption ? (
        <section
          className="space-y-2 border-l-2 border-amber-400 pl-3"
          aria-label="Przeniesienie odczytu do szkicu"
        >
          <h4 className="font-semibold">Nowy szkic z odczytu zdjęcia</h4>
          <p>
            {dirty
              ? "Masz niezapisane zmiany. Potwierdzenie zastąpi lokalne wpisy. "
              : ""}
            {adoption.will_replace_draft
              ? "Zapisany szkic zostanie zastąpiony nową rewizją; poprzedni pozostanie w historii. "
              : ""}
            Zatwierdzone pozycje i płatność pozostaną bez zmian.
          </p>
          <button
            type="button"
            className="btn-primary"
            disabled={busy || uncertain || !active}
            onClick={() => void run("import")}
          >
            Zastąp szkic odczytem
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={busy || uncertain}
            onClick={() => {
              setAdoption(null);
              onImportLockChange(false);
            }}
          >
            Zachowaj własny szkic
          </button>
        </section>
      ) : null}
      {message ? <p role="status">{message}</p> : null}
      {uncertain ? (
        <div className="space-y-2">
          <p>
            Zachowano klucz i treść tej próby w tej karcie. Odtworzenie nie
            tworzy nowej generacji. Zamknięcie panelu nie anuluje wysyłki.
          </p>
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !active}
            onClick={() => void run(intent.current!.action)}
          >
            Sprawdź tę samą próbę
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={busy || !active}
            onClick={() => {
              clearReceiptReadIntent(owner, billId);
              intent.current = null;
              setUncertain(false);
              setAdoption(null);
              onImportLockChange(false);
              setMessage(
                "Porzucono zachowaną próbę. Polecenie mogło już zostać zapisane; sprawdź aktualny wynik przed nową decyzją.",
              );
            }}
          >
            Porzuć zachowaną próbę
          </button>
        </div>
      ) : null}
    </section>
  );
}
