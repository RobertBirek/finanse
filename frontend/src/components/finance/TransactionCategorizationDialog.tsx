import { useState } from "react";
import type { AxiosError } from "axios";
import { useQueryClient, useIsMutating } from "@tanstack/react-query";
import { categoryPath } from "../../lib/categories";
import {
  useCategories,
  parsePlnToGrosze,
  invalidateFinanceLedger,
} from "../../api/finance";
import {
  type CategorizationContext,
  type CategoryPreview,
  useCategorization,
  usePreviewCategorization,
  useApplyCategorization,
} from "../../api/categorization";
import { useAuthStore } from "../../stores/authStore";
import { formatPLN } from "../../lib/format";
import { Dialog } from "../Dialog";
import { AssignmentOriginLabel } from "./AssignmentOriginLabel";
import { QueryFeedback } from "../QueryFeedback";
import { CategorySplitEditor, type SplitRow } from "./CategorySplitEditor";

export function TransactionCategorizationDialog({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const query = useCategorization(id);
  const busy =
    useIsMutating({ mutationKey: ["finance", "categorization", id] }) > 0;
  return (
    <Dialog
      label="Kategorie wydatku"
      busy={busy}
      onClose={onClose}
      panelClassName="card w-full max-w-xl"
    >
      <h2 className="text-lg font-semibold">Kategorie wydatku</h2>
      <QueryFeedback
        loading={query.isLoading}
        error={query.isError}
        errorMessage="Nie udało się pobrać podziału."
        onRetry={query.refetch}
      >
        {query.data ? (
          <ReviewedEditor key={id} context={query.data} onClose={onClose} />
        ) : null}
      </QueryFeedback>
      {!query.data ? (
        <button type="button" className="btn-secondary mt-3" onClick={onClose}>
          Zamknij
        </button>
      ) : null}
    </Dialog>
  );
}

function ReviewedEditor({
  context,
  onClose,
}: {
  context: CategorizationContext;
  onClose: () => void;
}) {
  const [snapshot] = useState(context);
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((state) => state.sessionVersion) === session;
  const cats = useCategories();
  const [rows, setRows] = useState<SplitRow[]>(() =>
    snapshot.parts.map((p, index) => ({
      key: String(index),
      category: p.category_id,
      amount: (p.amount_minor / 100).toFixed(2),
    })),
  );
  const [preview, setPreview] = useState<CategoryPreview | null>(null);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [failure, setFailure] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const check = usePreviewCategorization(snapshot.transaction_id);
  const apply = useApplyCategorization(snapshot.transaction_id);
  const client = useQueryClient();
  const busy = check.isPending || apply.isPending;
  const parsed = rows.map((row) => parsePlnToGrosze(row.amount));
  const total = parsed.reduce<number>((sum, value) => sum + (value ?? 0), 0);
  const valid =
    rows.length > 0 &&
    rows.length <= snapshot.max_parts &&
    parsed.every((value) => value !== null) &&
    Number.isSafeInteger(total) &&
    total === snapshot.amount_minor &&
    rows.every((row) => !!row.category) &&
    new Set(rows.map((row) => row.category)).size === rows.length;
  function error(error: unknown) {
    if (useAuthStore.getState().sessionVersion !== session) return;
    const response = (error as AxiosError<{ detail?: string }>).response;
    setFailure(
      typeof response?.data.detail === "string"
        ? response.data.detail
        : "Nie udało się zapisać. Zachowano wpisane wartości; ponowienie tej samej decyzji nie utworzy drugiej płatności.",
    );
    setStale(response?.status === 409);
  }
  function change(next: SplitRow[]) {
    setRows(next);
    setPreview(null);
    setKey(crypto.randomUUID());
    setFailure(null);
  }
  function closeAndRefresh() {
    if (useAuthStore.getState().sessionVersion === session) {
      invalidateFinanceLedger(client);
      client.invalidateQueries({ queryKey: ["finance", "categorization"] });
    }
    onClose();
  }
  return (
    <div className="mt-4 space-y-4">
      <AssignmentOriginLabel origin={snapshot.assignment_origin} />
      {!active ? (
        <p role="alert">
          Sesja zmieniła się. Zamknij okno i wczytaj aktualne dane.
        </p>
      ) : !snapshot.eligibility.allowed ? (
        <p>{snapshot.eligibility.message}</p>
      ) : (
        <>
          <p className="text-sm text-gray-300">
            Płatność:{" "}
            <strong className="font-mono">
              {formatPLN(snapshot.amount_minor ?? 0)} PLN
            </strong>
            . Saldo, daty i powiązania dokumentów pozostają bez zmian. Podział
            zmienia raporty i budżety, nie kategorię zapisaną na dokumencie.
          </p>
          {snapshot.source === "manual" ? (
            <p className="text-sm text-gray-400">
              Ręcznie zatwierdzony podział, wersja {snapshot.version}. Możesz
              zatwierdzić kolejną ręczną zmianę.
            </p>
          ) : null}
          <QueryFeedback
            loading={cats.isLoading}
            error={cats.isError}
            errorMessage="Nie udało się pobrać kategorii."
            onRetry={cats.refetch}
          >
            <CategorySplitEditor
              rows={rows}
              categories={cats.data ?? []}
              onChange={change}
              disabled={busy || stale}
              maxParts={snapshot.max_parts}
            />
          </QueryFeedback>
          <p aria-live="polite" className="text-sm font-mono">
            {Number.isSafeInteger(total) &&
            parsed.every((value) => value !== null)
              ? `Pozostało: ${formatPLN((snapshot.amount_minor ?? 0) - total)} PLN`
              : "Uzupełnij poprawne kwoty w groszach."}
          </p>
          {preview ? (
            <section
              aria-label="Podgląd podziału"
              className="rounded-lg border border-advisor-500/40 p-3 space-y-2"
            >
              <h3 className="font-semibold">Podgląd do zatwierdzenia</h3>
              <h4 className="text-sm font-semibold">Przed zmianą</h4>
              <ul>
                {preview.before_parts.map((p) => (
                  <li
                    key={p.category_id}
                    className="text-sm [overflow-wrap:anywhere]"
                  >
                    {categoryPath(p.category_id, cats.data ?? [])}:{" "}
                    <span className="font-mono">
                      {formatPLN(p.amount_minor)} PLN
                    </span>
                  </li>
                ))}
              </ul>
              <h4 className="text-sm font-semibold">Po zmianie</h4>
              <ul>
                {preview.after_parts.map((p) => (
                  <li
                    key={p.category_id}
                    className="text-sm [overflow-wrap:anywhere]"
                  >
                    {preview.target_paths[p.category_id]}:{" "}
                    <span className="font-mono">
                      {formatPLN(p.amount_minor)} PLN
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-sm text-gray-400">
                Zatwierdzasz jedną płatność z tym rozkładem kategorii. Agent nie
                nadpisze tej ręcznej decyzji.
              </p>
              <button
                className="btn-primary"
                type="button"
                disabled={busy || stale}
                onClick={() =>
                  apply.mutate(
                    {
                      id: snapshot.transaction_id,
                      key,
                      expected_version: preview.expected_version,
                      expected_preview_snapshot: preview.preview_snapshot,
                      parts: preview.after_parts,
                      confirmed: true,
                    },
                    {
                      onSuccess: () => {
                        if (useAuthStore.getState().sessionVersion === session)
                          onClose();
                      },
                      onError: error,
                    },
                  )
                }
              >
                Zatwierdź podział
              </button>
            </section>
          ) : (
            <button
              className="btn-primary"
              type="button"
              disabled={
                !valid || busy || stale || cats.isError || cats.isLoading
              }
              onClick={() =>
                check.mutate(
                  {
                    id: snapshot.transaction_id,
                    expected_version: snapshot.version,
                    expected_context_snapshot: snapshot.context_snapshot,
                    parts: rows.map((row, index) => ({
                      category_id: row.category,
                      amount_minor: parsed[index]!,
                    })),
                  },
                  {
                    onSuccess: (value) => {
                      if (useAuthStore.getState().sessionVersion === session)
                        setPreview(value);
                    },
                    onError: error,
                  },
                )
              }
            >
              Sprawdź podział
            </button>
          )}
          {failure ? (
            <p role="alert" className="text-red-300">
              {failure}
            </p>
          ) : null}
          {stale ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={closeAndRefresh}
            >
              Zamknij i odśwież
            </button>
          ) : null}
        </>
      )}
      <button
        type="button"
        className="btn-secondary"
        disabled={busy}
        onClick={onClose}
      >
        Zamknij
      </button>
    </div>
  );
}
