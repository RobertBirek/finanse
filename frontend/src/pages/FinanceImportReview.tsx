import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  importError,
  useImport,
  useImportAccounts,
  useImportCategories,
  useImportActor,
  useImportRows,
  useSaveImportDecisions,
  usePreviewImport,
  usePrepareImportSource,
  useCommitImport,
  useImportCommandResult,
  importQueryKey,
  type ImportBatch,
  type ImportDecision,
  type ImportRow,
  type ImportPreview as PreviewData,
  type CommitResult,
} from "../api/bankImports";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { ImportUpload } from "../components/finance/imports/ImportUpload";
import { ImportSources } from "../components/finance/imports/ImportSources";
import { isSourceBlocked } from "../components/finance/imports/importPresentation";
import { ImportRows } from "../components/finance/imports/ImportRows";
import { ImportGroupEditor } from "../components/finance/imports/ImportGroupEditor";
import { ImportPreview } from "../components/finance/imports/ImportPreview";
import { ImportReceipt } from "../components/finance/imports/ImportReceipt";
import { ScheduleImportWorkspace } from "../components/finance/imports/ScheduleImportWorkspace";
import { invalidateFinanceLedger } from "../api/finance";
import { isProcessingActorCurrent } from "../stores/documentProcessingStore";

function Workspace({ batch }: { batch: ImportBatch }) {
  const [params] = useSearchParams();
  const accounts = useImportAccounts();
  const categories = useImportCategories();
  const [sourceId, setSource] = useState<string | null>(null);
  const [comparisonRevision, setComparisonRevision] = useState<string | null>(
    null,
  );
  const [offset, setOffset] = useState(0);
  const publication = `${batch.version}:${batch.sources
    .map(
      (source) =>
        `${source.id}:${source.current_revision_id}:${source.candidate_revision_id}:${source.processing_state}`,
    )
    .sort()
    .join("|")}`;
  const rows = useImportRows(
    batch.id,
    {
      source_id: sourceId ?? undefined,
      revision_id: comparisonRevision ?? undefined,
      offset,
      limit: 100,
    },
    publication,
  );
  const [selectedRows, setRows] = useState<Map<string, ImportRow>>(new Map());
  const [selection, setSelection] = useState<{
    version: number;
    ids: string[];
  } | null>(null);
  const groupIds =
    selection?.version === batch.version
      ? selection.ids
      : batch.groups
          .filter((group) => group.state === "ready")
          .map((group) => group.id);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [receipt, setReceipt] = useState<CommitResult | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [requiredAcks, setRequiredAcks] = useState<string[]>([]);
  const [acks, setAcks] = useState<string[]>([]);
  const intent = useRef<{ previewId: string; key: string } | null>(null);
  const { ownerId, generation } = useImportActor();
  const client = useQueryClient();
  const recovered = useImportCommandResult(
    batch.id,
    uncertain ? (intent.current?.key ?? null) : null,
  );
  const recoveryApplied = useRef<string | null>(null);
  useEffect(() => {
    const actor = { ownerId, generation };
    const result = recovered.data;
    if (
      !result ||
      !preview ||
      !isProcessingActorCurrent(actor) ||
      result.batch_id !== batch.id ||
      result.request_hash !== preview.request_hash ||
      !result.receipt_id ||
      recoveryApplied.current === result.receipt_id
    )
      return;
    recoveryApplied.current = result.receipt_id;
    setReceipt(result);
    setUncertain(false);
    setProblem(null);
    invalidateFinanceLedger(client);
    client.invalidateQueries({ queryKey: importQueryKey(actor) });
  }, [recovered.data, preview, ownerId, generation, batch.id, client]);
  const save = useSaveImportDecisions();
  const prepare = usePreviewImport();
  const parseSource = usePrepareImportSource();
  const commit = useCommitImport();
  const busy =
    save.isPending ||
    prepare.isPending ||
    commit.isPending ||
    parseSource.isPending;
  const knownRows = new Map([
    ...(rows.data?.items ?? []).map((row) => [row.id, row] as const),
    ...selectedRows,
  ]);
  const blocked = groupIds.some((id) =>
    batch.groups
      .find((group) => group.id === id)
      ?.row_ids.some((rowId) => {
        const row = knownRows.get(rowId);
        const source = batch.sources.find(
          (source) => source.id === row?.source_id,
        );
        return (
          source &&
          (isSourceBlocked(source) || source.processing_state !== "ready")
        );
      }),
  );
  const currentPreview =
    !!preview &&
    !comparisonRevision &&
    preview.version === batch.version &&
    [...groupIds].sort().join(",") ===
      preview.groups
        .map((group) => group.group_id)
        .sort()
        .join(",");
  function report(error: unknown) {
    const data = (error as AxiosError<{ code?: string; detail?: string }>)
      .response?.data;
    if (data?.code === "import_acknowledgement_required") {
      setRequiredAcks(
        data.detail?.match(
          /(?:opening_gap|possible_duplicate|transfer_date_difference):[^\s,]+/g,
        ) ?? [],
      );
    }
    if ((error as AxiosError).response?.status === 409) setPreview(null);
    setProblem(importError(error));
  }
  async function saveDecision(decision: ImportDecision) {
    if (uncertain || comparisonRevision) return;
    setProblem(null);
    setPreview(null);
    intent.current = null;
    try {
      await save.mutateAsync({
        batchId: batch.id,
        idempotencyKey: crypto.randomUUID(),
        data: { expected_version: batch.version, decisions: [decision] },
      });
      setRows(new Map());
    } catch (error) {
      report(error);
    }
  }
  async function requestParse(sourceId: string) {
    if (uncertain || busy || batch.archived_at) return;
    setProblem(null);
    try {
      await parseSource.mutateAsync({
        batchId: batch.id,
        sourceId,
        idempotencyKey: crypto.randomUUID(),
      });
    } catch (error) {
      report(error);
    }
  }
  async function preparePreview() {
    if (uncertain || comparisonRevision) return;
    setProblem(null);
    intent.current = null;
    try {
      const result = await prepare.mutateAsync({
        batchId: batch.id,
        idempotencyKey: crypto.randomUUID(),
        data: {
          expected_version: batch.version,
          group_ids: groupIds,
          acknowledgements: acks,
        },
      });
      setPreview(result);
    } catch (error) {
      report(error);
    }
  }
  async function commitPreview() {
    if (!preview || !currentPreview || busy) return;
    setProblem(null);
    if (intent.current?.previewId !== preview.id)
      intent.current = { previewId: preview.id, key: crypto.randomUUID() };
    try {
      const result = await commit.mutateAsync({
        batchId: batch.id,
        idempotencyKey: intent.current.key,
        data: { preview_id: preview.id, request_hash: preview.request_hash },
      });
      setReceipt(result);
      setUncertain(false);
    } catch (error) {
      const status = (error as AxiosError).response?.status;
      setUncertain(!status || status >= 500 || status === 408);
      report(error);
    }
  }
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap justify-between gap-3">
        <p>
          Źródła: {batch.sources.length} · Otwarte wiersze:{" "}
          {batch.unresolved_count} · Wersja decyzji: {batch.version}
        </p>
        <Link className="underline" to="/finances/imports">
          Wszystkie importy
        </Link>
      </div>
      {receipt ? <ImportReceipt receipt={receipt} /> : null}
      {uncertain ? (
        <section className="card space-y-3">
          <p role="status" className="card">
            Nie potwierdzono jeszcze wyniku zapisu. Nie twórz nowej decyzji.
            Ponów zatwierdzenie poniżej — użyjemy tego samego klucza i
            sprawdzimy trwały wynik.
          </p>
          <button
            type="button"
            className="btn-secondary"
            disabled={recovered.isFetching}
            onClick={() => recovered.refetch()}
          >
            Sprawdź zapisany wynik
          </button>
          {recovered.isError ? (
            <p className="text-sm">
              Potwierdzenie nie jest jeszcze dostępne. Możesz sprawdzić ponownie
              bez tworzenia nowej operacji.
            </p>
          ) : null}
        </section>
      ) : null}
      {problem ? (
        <p role="alert" className="card break-words">
          {problem}
        </p>
      ) : null}
      {batch.archived_at ? (
        <p className="card">
          Import jest archiwalny. Zachowano źródła i historię.
        </p>
      ) : (
        <ImportUpload batchId={batch.id} disabled={uncertain || busy} />
      )}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(15rem,1fr)_minmax(0,2.4fr)]">
        <ImportSources
          sources={batch.sources}
          disabled={uncertain || busy || !!batch.archived_at}
          onPrepare={requestParse}
          selected={sourceId}
          onSelect={(id) => {
            setSource(id);
            setComparisonRevision(null);
            setOffset(0);
          }}
          onCompare={(source) => {
            setSource(source.id);
            setComparisonRevision(source.candidate_revision_id ?? null);
            setOffset(0);
          }}
        />
        <div className="min-w-0 space-y-5">
          {comparisonRevision ? (
            <section className="card space-y-2">
              <p>
                Porównujesz ponowny odczyt. Nie jest wersją bieżącą i nie może
                zostać zatwierdzony. Zmienione wiersze wymagają rozstrzygnięcia,
                nie zastępują historii.
              </p>
              <button
                className="btn-secondary"
                type="button"
                onClick={() => {
                  setComparisonRevision(null);
                  setOffset(0);
                }}
              >
                Wróć do bieżącego odczytu
              </button>
            </section>
          ) : null}
          {rows.isError ? (
            <p role="alert" className="card">
              Nie udało się pobrać wierszy.{" "}
              <button
                className="underline"
                type="button"
                onClick={() => rows.refetch()}
              >
                Ponów odczyt
              </button>
            </p>
          ) : rows.isLoading ? (
            <p role="status">Ładowanie wierszy…</p>
          ) : (
            <ImportRows
              readOnly={
                !!comparisonRevision || uncertain || busy || !!batch.archived_at
              }
              rows={rows.data?.items ?? []}
              selectedIds={new Set(selectedRows.keys())}
              onSelect={(row, checked) => {
                setRows((current) => {
                  const next = new Map(current);
                  if (checked) next.set(row.id, row);
                  else next.delete(row.id);
                  return next;
                });
              }}
            />
          )}
          {rows.data && rows.data.total > 100 ? (
            <div className="flex items-center justify-between gap-2">
              <button
                className="btn-secondary"
                disabled={offset === 0}
                onClick={() =>
                  setOffset((current) => Math.max(0, current - 100))
                }
              >
                Poprzednie wiersze
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 100, rows.data.total)} z{" "}
                {rows.data.total}
              </span>
              <button
                className="btn-secondary"
                disabled={offset + 100 >= rows.data.total}
                onClick={() => setOffset((current) => current + 100)}
              >
                Następne wiersze
              </button>
            </div>
          ) : null}
          {selectedRows.size && !batch.archived_at && !comparisonRevision ? (
            <ImportGroupEditor
              key={`${batch.version}:${[...selectedRows.keys()].join(",")}`}
              batchId={batch.id}
              rows={[...selectedRows.values()]}
              accounts={accounts.data ?? []}
              categories={categories.data ?? []}
              sources={batch.sources}
              accountSuggestion={params.get("account")}
              pending={busy || uncertain}
              onSave={saveDecision}
            />
          ) : null}
          <section className="card space-y-3" aria-label="Wybrane grupy">
            <h2 className="text-xl">Grupy do zatwierdzenia</h2>
            <p className="text-sm">
              Zaznacz kompletne grupy. Transfer, FX i jego opłaty zapisują się
              razem.
            </p>
            {batch.groups.map((group) => (
              <label
                className="flex items-start gap-2 break-all text-sm"
                key={group.id}
              >
                <input
                  type="checkbox"
                  aria-label={`Wybierz grupę ${group.id}`}
                  checked={groupIds.includes(group.id)}
                  disabled={
                    group.state !== "ready" ||
                    busy ||
                    uncertain ||
                    !!batch.archived_at
                  }
                  onChange={(event) => {
                    setSelection({
                      version: batch.version,
                      ids: event.target.checked
                        ? [...groupIds, group.id]
                        : groupIds.filter((id) => id !== group.id),
                    });
                    setPreview(null);
                    intent.current = null;
                  }}
                />
                {group.state === "committed"
                  ? "Zatwierdzona"
                  : group.state === "deferred"
                    ? "Pozostawiona otwarta"
                    : (group.decision?.kind ?? "Niesklasyfikowana")}{" "}
                · {group.row_ids.length} wierszy
              </label>
            ))}
            {batch.groups.length === 0 ? (
              <p>
                Zaznacz wiersz lub obie nogi wymiany powyżej i zapisz decyzję.
              </p>
            ) : null}
            {requiredAcks.map((ack) => (
              <label className="flex items-start gap-2 text-sm" key={ack}>
                <input
                  type="checkbox"
                  checked={acks.includes(ack)}
                  disabled={uncertain || busy}
                  onChange={(event) => {
                    setAcks((current) =>
                      event.target.checked
                        ? [...current, ack]
                        : current.filter((value) => value !== ack),
                    );
                    setPreview(null);
                  }}
                />
                {ack.startsWith("opening_gap:")
                  ? "Różnica salda otwarcia — akceptuję otwarte uzgodnienie bez korekty salda"
                  : ack.startsWith("possible_duplicate:")
                    ? "Możliwe dopasowanie — sprawdziłem i wybieram odrębną operację"
                    : "Potwierdzam różne daty rzeczywistych nóg transferu"}
              </label>
            ))}
            <button
              type="button"
              className="btn-primary"
              disabled={
                busy ||
                uncertain ||
                !!comparisonRevision ||
                rows.isLoading ||
                rows.isError ||
                blocked ||
                groupIds.length === 0 ||
                !!batch.archived_at
              }
              onClick={preparePreview}
            >
              Przygotuj podgląd
            </button>
          </section>
          {preview ? (
            <ImportPreview
              key={preview.id}
              preview={preview}
              current={currentPreview}
              pending={commit.isPending}
              onCommit={commitPreview}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function FinanceImportReview() {
  const { batchId } = useParams();
  const actor = useImportActor();
  const batch = useImport(batchId ?? null);
  return (
    <div className="max-w-6xl">
      <header className="finance-page-heading">
        <div>
          <h1>
            {batch.data?.kind === "loan_schedule"
              ? "Weryfikacja harmonogramu"
              : "Weryfikacja wyciągu"}
          </h1>
          <p>
            Oryginał pozostaje bez zmian. Decyzje i podgląd nie księgują
            operacji.
          </p>
        </div>
      </header>
      <FinanceTabs />
      {batch.isLoading ? (
        <p role="status">Ładowanie importu…</p>
      ) : batch.isError || !batch.data ? (
        <p role="alert" className="card">
          Nie udało się otworzyć importu. Sprawdź dostęp lub{" "}
          <button
            type="button"
            className="underline"
            onClick={() => batch.refetch()}
          >
            spróbuj ponownie
          </button>
          .
        </p>
      ) : batch.data.kind === "loan_schedule" ? (
        <ScheduleImportWorkspace
          key={`${actor.ownerId}:${actor.generation}:${batchId}`}
          batch={batch.data}
        />
      ) : (
        <Workspace
          key={`${actor.ownerId}:${actor.generation}:${batchId}`}
          batch={batch.data}
        />
      )}
    </div>
  );
}
