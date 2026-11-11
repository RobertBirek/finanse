import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import type { AxiosError } from "axios";
import {
  importError,
  importQueryKey,
  useImportAccounts,
  useImportActor,
  useImportRows,
  usePrepareImportSource,
  type ImportBatch,
} from "../../../api/bankImports";
import {
  invalidateScheduleQueries,
  useActivateSchedule,
  useScheduleCommandResult,
  useScheduleLoan,
  useScheduleLoans,
  useSchedulePreview,
  validScheduleResult,
  type SchedulePreview,
  type ScheduleResult,
  type ScheduleRow,
  type ScheduleTargetData,
} from "../../../api/loanScheduleImports";
import { isProcessingActorCurrent } from "../../../stores/documentProcessingStore";
import { formatPLN } from "../../../lib/format";
import { ImportSources } from "./ImportSources";
import { isSourceBlocked } from "./importPresentation";
import { ScheduleTarget } from "./ScheduleTarget";
import { validScheduleTarget } from "./scheduleTargetValidation";
import { ScheduleDiff } from "./ScheduleDiff";
import { ScheduleConfirmation } from "./ScheduleConfirmation";
import { ScheduleReceipt } from "./ScheduleReceipt";
import { ScheduleSourceComparison } from "./ScheduleSourceComparison";

export function ScheduleImportWorkspace({ batch }: { batch: ImportBatch }) {
  const actor = useImportActor();
  const { ownerId, generation } = actor;
  const client = useQueryClient();
  const [params] = useSearchParams();
  const [target, setTarget] = useState<ScheduleTargetData>(() => ({
    loan_id: params.get("loan"),
    new_loan: null,
  }));
  const accounts = useImportAccounts();
  const loans = useScheduleLoans();
  const detail = useScheduleLoan(target.loan_id);
  const [selection, setSelection] = useState<string | null>(null);
  const source =
    batch.sources.find((s) => s.id === selection) ?? batch.sources[0];
  const [revisionChoice, setRevisionChoice] = useState<{
    sourceId: string;
    id: string;
  } | null>(null);
  const [comparisonAck, setComparisonAck] = useState<string | null>(null);
  const revisionId =
    revisionChoice?.sourceId === source?.id &&
    [source?.current_revision_id, source?.candidate_revision_id].includes(
      revisionChoice.id,
    )
      ? revisionChoice.id
      : source?.current_revision_id;
  const comparing =
    !!source?.candidate_revision_id &&
    revisionId === source.candidate_revision_id;
  const comparisonToken = source?.candidate_revision_id
    ? `reparse_comparison:${source.id}:${source.candidate_revision_id}`
    : null;
  const previousRows = useImportRows(
    comparing ? batch.id : null,
    {
      source_id: source?.id,
      revision_id: source?.current_revision_id ?? undefined,
      limit: 1000,
    },
    batch.version,
  );
  const candidateRows = useImportRows(
    comparing ? batch.id : null,
    {
      source_id: source?.id,
      revision_id: source?.candidate_revision_id ?? undefined,
      limit: 1000,
    },
    batch.version,
  );
  const comparisonLoaded =
    !!previousRows.data &&
    !!candidateRows.data &&
    !previousRows.isError &&
    !candidateRows.isError &&
    previousRows.data.items.length === previousRows.data.total &&
    candidateRows.data.items.length === candidateRows.data.total;
  const stored = (
    source?.schedule_activations?.find(
      (a) => a.source_revision_id === revisionId,
    ) ?? (!revisionChoice ? source?.schedule_activations?.[0] : undefined)
  )?.result;
  const [offset, setOffset] = useState(0);
  const rows = useImportRows(
    batch.id,
    {
      source_id: source?.id,
      revision_id: revisionId ?? undefined,
      offset,
      limit: 100,
    },
    batch.version,
  );
  const [ack, setAck] = useState(false);
  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [receipt, setReceipt] = useState<ScheduleResult | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const intent = useRef<{ previewId: string; key: string } | null>(null);
  const recoveryApplied = useRef<string | null>(null);
  const prepare = useSchedulePreview();
  const activate = useActivateSchedule();
  const parse = usePrepareImportSource();
  const busy = prepare.isPending || activate.isPending || parse.isPending;
  const recovered = useScheduleCommandResult(
    batch.id,
    uncertain ? (intent.current?.key ?? null) : null,
  );
  useEffect(() => {
    const captured = { ownerId, generation };
    if (
      !recovered.data ||
      !preview ||
      !isProcessingActorCurrent(captured) ||
      recoveryApplied.current === recovered.data.receipt_id
    )
      return;
    try {
      const result = validScheduleResult(
        recovered.data,
        batch.id,
        preview.request_hash,
      );
      recoveryApplied.current = result.receipt_id;
      setReceipt(result);
      setUncertain(false);
      setProblem(null);
      invalidateScheduleQueries(client, captured);
      void client.invalidateQueries({ queryKey: importQueryKey(captured) });
    } catch {
      /* Only a matching receipt may resolve an uncertain intent. */
    }
  }, [recovered.data, preview, ownerId, generation, batch.id, client]);
  const current =
    !!preview &&
    preview.version === batch.version &&
    preview.source_revision_id === revisionId;
  const ready =
    source?.processing_state === "ready" &&
    !isSourceBlocked(
      comparing
        ? { ...source, checks: source.candidate_checks ?? source.checks }
        : source,
    ) &&
    (!source.candidate_revision_id ||
      (comparing && comparisonLoaded && comparisonAck === comparisonToken));
  const mapped = validScheduleTarget(
    target,
    loans.data ?? [],
    accounts.data ?? [],
  );
  function changeTarget(value: ScheduleTargetData) {
    setTarget(value);
    setAck(false);
    setPreview(null);
    intent.current = null;
    setProblem(null);
  }
  async function makePreview() {
    if (!source || !ready || !mapped || !ack || busy || uncertain) return;
    setProblem(null);
    intent.current = null;
    try {
      const value = await prepare.mutateAsync({
        batchId: batch.id,
        idempotencyKey: crypto.randomUUID(),
        data: {
          expected_version: batch.version,
          source_id: source.id,
          source_revision_id: revisionId,
          target,
          acknowledgements: [
            `schedule_target:${source.id}`,
            ...(comparing && comparisonToken ? [comparisonToken] : []),
          ],
        },
      });
      if (isProcessingActorCurrent(actor)) setPreview(value);
    } catch (error) {
      if (isProcessingActorCurrent(actor)) {
        setPreview(null);
        setProblem(importError(error));
      }
    }
  }
  async function commit() {
    if (!preview || !current || busy || preview.existing_activation) return;
    setProblem(null);
    if (intent.current?.previewId !== preview.id)
      intent.current = { previewId: preview.id, key: crypto.randomUUID() };
    try {
      const result = await activate.mutateAsync({
        batchId: batch.id,
        idempotencyKey: intent.current.key,
        data: { preview_id: preview.id, request_hash: preview.request_hash },
      });
      if (isProcessingActorCurrent(actor)) {
        setReceipt(result);
        setUncertain(false);
      }
    } catch (error) {
      if (!isProcessingActorCurrent(actor)) return;
      const status = (error as AxiosError).response?.status;
      setProblem(importError(error));
      if (status && status < 500 && status !== 408) {
        setPreview(null);
        intent.current = null;
        setUncertain(false);
      } else setUncertain(true);
    }
  }
  if (receipt) return <ScheduleReceipt result={receipt} />;
  return (
    <div className="space-y-5">
      <p className="card font-medium">Harmonogram nie księguje spłat</p>
      <ImportSources
        sources={batch.sources}
        selected={source?.id ?? null}
        disabled={busy || uncertain || !!batch.archived_at}
        onSelect={(id) => {
          if (busy || uncertain) return;
          setSelection(id);
          setOffset(0);
          setPreview(null);
          setAck(false);
          setRevisionChoice(null);
          setComparisonAck(null);
          intent.current = null;
        }}
        onPrepare={async (id) => {
          if (busy || uncertain) return;
          setPreview(null);
          try {
            await parse.mutateAsync({
              batchId: batch.id,
              sourceId: id,
              idempotencyKey: crypto.randomUUID(),
            });
          } catch (e) {
            setProblem(importError(e));
          }
        }}
      />
      {source?.candidate_revision_id ? (
        <section className="card space-y-3">
          <label className="block">
            Odczyt harmonogramu
            <select
              className="input mt-1 w-full"
              value={revisionId ?? ""}
              disabled={busy || uncertain}
              onChange={(e) => {
                setRevisionChoice({ sourceId: source.id, id: e.target.value });
                setComparisonAck(null);
                setPreview(null);
                intent.current = null;
                setOffset(0);
              }}
            >
              <option value={source.current_revision_id ?? ""}>
                Zachowany odczyt · {source.parser_version}
              </option>
              <option value={source.candidate_revision_id}>
                Kandydat · {source.candidate_parser_version}
              </option>
            </select>
          </label>
          <p className="text-sm">
            Kandydat wymaga wyboru i porównania. Zachowany odczyt oraz
            poprzednie wersje pozostaną niezmienione.
          </p>
        </section>
      ) : null}
      {comparing ? (
        <>
          <ScheduleSourceComparison
            previous={previousRows.data?.items ?? []}
            candidate={candidateRows.data?.items ?? []}
            loading={previousRows.isLoading || candidateRows.isLoading}
            error={
              !comparisonLoaded &&
              !previousRows.isLoading &&
              !candidateRows.isLoading
            }
          />
          <label className="card flex items-start gap-2">
            <input
              type="checkbox"
              disabled={!comparisonLoaded || busy || uncertain}
              checked={comparisonAck === comparisonToken}
              onChange={(e) => {
                setComparisonAck(e.target.checked ? comparisonToken : null);
                setPreview(null);
                intent.current = null;
              }}
            />
            Porównałem odczyty z oryginałem i świadomie wybieram wskazaną
            rewizję kandydującą
          </label>
        </>
      ) : null}
      {stored ? (
        <ScheduleReceipt result={stored} />
      ) : (
        <>
          {accounts.isError || loans.isError ? (
            <p role="alert">
              Nie udało się pobrać kont lub umów. Odśwież import.
            </p>
          ) : null}
          {accounts.isLoading || loans.isLoading ? (
            <p className="card" role="status">
              Ładowanie kont i umów…
            </p>
          ) : (
            <ScheduleTarget
              value={target}
              onChange={changeTarget}
              loans={loans.data ?? []}
              accounts={accounts.data ?? []}
              disabled={busy || uncertain || !!batch.archived_at}
            />
          )}
          <section className="card space-y-3" aria-label="Raty źródłowe">
            <h2 className="text-xl">
              Numer bankowy w wersji — nie identyfikator wpłaty
            </h2>
            <p className="text-sm">
              Numery wewnętrzne i UUID istniejących rat nie zostaną przepisane.
            </p>
            {rows.isLoading ? (
              <p role="status">Ładowanie rat…</p>
            ) : rows.isError ? (
              <p role="alert">Nie udało się pobrać rat źródłowych.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      {[
                        "Numer bankowy",
                        "Termin",
                        "Kapitał PLN",
                        "Odsetki PLN",
                        "Opłaty PLN",
                        "Razem PLN",
                      ].map((t) => (
                        <th key={t} className="p-2 text-left">
                          {t}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(rows.data?.items ?? []).map((item) => {
                      const r =
                        item.schedule_fields as unknown as ScheduleRow | null;
                      return r ? (
                        <tr key={item.id}>
                          <td className="p-2">{r.bank_number}</td>
                          <td className="p-2 whitespace-nowrap">
                            {r.due_date}
                          </td>
                          {[r.principal, r.interest, r.fees, r.total].map(
                            (v, i) => (
                              <td
                                className="p-2 text-right font-mono whitespace-nowrap"
                                key={i}
                              >
                                {formatPLN(v)}
                              </td>
                            ),
                          )}
                        </tr>
                      ) : null;
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div className="flex gap-3">
              <button
                className="btn-secondary"
                disabled={!offset || busy}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Poprzednie raty
              </button>
              <button
                className="btn-secondary"
                disabled={offset + 100 >= (rows.data?.total ?? 0) || busy}
                onClick={() => setOffset(offset + 100)}
              >
                Następne raty
              </button>
            </div>
          </section>
          <section className="card space-y-4">
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={ack}
                disabled={busy || uncertain || !!batch.archived_at}
                onChange={(e) => {
                  setAck(e.target.checked);
                  setPreview(null);
                  intent.current = null;
                }}
              />
              Sprawdziłem przypisanie harmonogramu do kredytu i wskazanych kont
            </label>
            <button
              className="btn-primary"
              type="button"
              disabled={
                !ready ||
                !mapped ||
                !ack ||
                busy ||
                uncertain ||
                rows.isLoading ||
                rows.isError ||
                !!batch.archived_at
              }
              onClick={makePreview}
            >
              {prepare.isPending
                ? "Przygotowywanie…"
                : "Przygotuj podgląd harmonogramu"}
            </button>
          </section>
          {problem ? (
            <p role="alert" className="card">
              {problem}
            </p>
          ) : null}
          {uncertain ? (
            <section className="card space-y-2">
              <p>
                Wynik niepewny. Nie twórz nowej decyzji; sprawdź zapisane
                potwierdzenie.
              </p>
              <button
                className="btn-secondary"
                onClick={() => recovered.refetch()}
              >
                Sprawdź potwierdzenie
              </button>
              <button
                className="btn-secondary"
                disabled={busy}
                onClick={commit}
              >
                Ponów tę samą decyzję
              </button>
            </section>
          ) : null}
          {preview?.existing_activation ? (
            <section className="space-y-3">
              <h2 className="text-xl">Odczyt zgodny z zapisaną wersją</h2>
              <p>
                Nie tworzymy kolejnej wersji ani rat. Poniżej oryginalne
                potwierdzenie tej aktywacji.
              </p>
              <ScheduleReceipt result={preview.existing_activation} />
            </section>
          ) : preview ? (
            <>
              <ScheduleDiff
                diff={preview.diff}
                installments={detail.data?.installments}
              />
              <ScheduleConfirmation
                key={preview.id}
                preview={preview}
                current={current && !uncertain}
                pending={activate.isPending}
                onActivate={commit}
              />
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
