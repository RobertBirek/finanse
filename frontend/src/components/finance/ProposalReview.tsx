import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { AxiosError } from "axios";
import {
  useApplyProposal,
  usePreviewProposal,
  useRejectProposal,
} from "../../api/categoryProposals";
import type {
  ProposalDetail,
  ProposalPreview,
  ProposalApplyInput,
} from "../../api/categoryProposals";
import { useCategories } from "../../api/finance";
import { useAuthStore } from "../../stores/authStore";
import { formatPLN } from "../../lib/format";
import { TransactionCategorizationDialog } from "./TransactionCategorizationDialog";
import type { CategoryPart } from "../../api/categorization";

type Outcome = "not_attempted" | "approved" | "stale" | "blocked" | "unknown";
interface ReviewedItem {
  proposal: ProposalDetail;
  preview: ProposalPreview;
  input: ProposalApplyInput;
  outcome: Outcome;
}
const labels: Record<Outcome, string> = {
  not_attempted: "Nie podjęto",
  approved: "Zatwierdzono",
  stale: "Dane zmieniły się — sprawdź ponownie",
  blocked: "Zablokowano — sprawdź ręcznie",
  unknown: "Wynik nieznany — ponów tę samą decyzję",
};

export function ProposalReview({
  items,
  maxItems,
  onNextPage,
  onFirstPage,
}: {
  items: ProposalDetail[];
  maxItems: number;
  onNextPage?: () => void;
  onFirstPage?: () => void;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const categories = useCategories();
  const [selected, setSelected] = useState<string[]>([]);
  const [review, setReview] = useState<ReviewedItem[] | null>(null);
  const reviewRef = useRef<ReviewedItem[] | null>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [manual, setManual] = useState<string | null>(null);
  const rejects = useRef(new Map<string, { key: string; version: number }>());
  const [rejectUnknown, setRejectUnknown] = useState<string | null>(null);
  const preview = usePreviewProposal();
  const apply = useApplyProposal();
  const reject = useRejectProposal();
  const isCurrent = () => useAuthStore.getState().sessionVersion === session;
  function partsLabel(parts: CategoryPart[]) {
    return parts
      .map(
        (p) =>
          `${categories.data?.find((c) => c.id === p.category_id)?.name ?? "Kategoria źródłowa"}: ${formatPLN(p.amount_minor)} zł`,
      )
      .join(" + ");
  }
  function store(value: ReviewedItem[] | null) {
    reviewRef.current = value;
    setReview(value);
  }
  async function prepare() {
    if (busyRef.current || !isCurrent()) return;
    busyRef.current = true;
    setBusy(true);
    setFailure(null);
    const rows = items
      .filter((i) => selected.includes(i.id) && i.eligible)
      .slice(0, maxItems);
    try {
      const ready = await Promise.all(
        rows.map(async (proposal) => {
          const p = await preview.mutateAsync({
            session,
            id: proposal.id,
            version: proposal.version,
          });
          return {
            proposal,
            preview: p,
            input: {
              session,
              id: proposal.id,
              key: crypto.randomUUID(),
              expected_version: p.expected_version,
              preview_snapshot: p.preview_snapshot,
              confirmed: true as const,
            },
            outcome: "not_attempted" as const,
          };
        }),
      );
      if (isCurrent() && ready.length) store(ready);
    } catch {
      if (isCurrent())
        setFailure(
          "Nie udało się przygotować podglądu. Sprawdź aktualne propozycje i wybierz je ponownie.",
        );
    } finally {
      busyRef.current = false;
      if (isCurrent()) setBusy(false);
    }
  }
  async function run() {
    if (busyRef.current || !isCurrent() || !reviewRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setAttempted(true);
    setFailure(null);
    let list = reviewRef.current;
    try {
      for (let index = 0; index < list.length; index++) {
        const row = list[index];
        if (row.outcome !== "unknown" && row.outcome !== "not_attempted")
          continue;
        if (!isCurrent()) break;
        let outcome: Outcome = "approved",
          stop = false;
        try {
          await apply.mutateAsync(row.input);
        } catch (error) {
          const status = (error as AxiosError).response?.status;
          outcome =
            status === 409
              ? "stale"
              : !status || status >= 500
                ? "unknown"
                : "blocked";
          stop = outcome === "unknown" || status === 401 || status === 403;
        }
        if (!isCurrent()) break;
        list = list.map((r, i) => (i === index ? { ...r, outcome } : r));
        store(list);
        if (stop) break;
      }
    } finally {
      busyRef.current = false;
      if (isCurrent()) setBusy(false);
    }
  }
  async function dismiss(row: ProposalDetail) {
    if (busyRef.current || !isCurrent()) return;
    const input = rejects.current.get(row.id) ?? {
      key: crypto.randomUUID(),
      version: row.version,
    };
    rejects.current.set(row.id, input);
    busyRef.current = true;
    setBusy(true);
    setFailure(null);
    try {
      await reject.mutateAsync({
        session,
        id: row.id,
        key: input.key,
        expected_version: input.version,
      });
      if (isCurrent()) setRejectUnknown(null);
    } catch (error) {
      if (isCurrent()) {
        const status = (error as AxiosError).response?.status;
        if (!status || status >= 500) setRejectUnknown(row.id);
        else rejects.current.delete(row.id);
        setFailure(
          !status || status >= 500
            ? "Wynik odrzucenia nieznany. Ponów z zachowanym kluczem."
            : "Nie udało się odrzucić. Wczytaj aktualną propozycję.",
        );
      }
    } finally {
      busyRef.current = false;
      if (isCurrent()) setBusy(false);
    }
  }
  function close() {
    store(null);
    setSelected([]);
    setAttempted(false);
    setFailure(null);
  }
  return (
    <section aria-label="Przegląd propozycji" className="space-y-4">
      {!active ? (
        <p role="alert">Sesja zmieniła się. Wczytaj aktualne dane.</p>
      ) : null}
      {failure ? (
        <p role="alert" className="text-sm text-red-400">
          {failure}
        </p>
      ) : null}
      {review ? (
        <>
          <h2 className="text-lg font-semibold">
            Sprawdź zmianę każdej kategorii
          </h2>
          <p className="text-sm text-gray-400">
            Zatwierdzasz tylko te pozycje. Kwoty, konta i daty nie zmienią się.
            Część decyzji może zostać zapisana nawet wtedy, gdy kolejna pozycja
            wymaga ponownego sprawdzenia.
          </p>
          <ul className="space-y-3">
            {review.map((r) => (
              <li
                key={r.proposal.id}
                className="card space-y-2 [overflow-wrap:anywhere]"
              >
                <h3 className="font-semibold">{r.proposal.description}</h3>
                <p>{formatPLN(r.preview.amount_minor)} zł</p>
                <p className="text-sm">
                  {partsLabel(r.preview.before_parts)} →{" "}
                  <strong>{r.preview.target_path}</strong>
                </p>
                <p className="text-sm text-gray-400">{r.preview.explanation}</p>
                <p className="text-xs text-gray-400">
                  Pewność modelu: {r.preview.confidence}. To informacja, nie
                  zgoda na zapis.
                </p>
                {attempted ? <p role="status">{labels[r.outcome]}</p> : null}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-3">
            {!attempted ? (
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !active}
                onClick={() => void run()}
              >
                Zatwierdź wybrane ({review.length})
              </button>
            ) : review.some(
                (r) => r.outcome === "unknown" || r.outcome === "not_attempted",
              ) ? (
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !active}
                onClick={() => void run()}
              >
                Ponów niedokończone
              </button>
            ) : null}
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={close}
            >
              {attempted ? "Porzuć niedokończony przegląd" : "Zmień wybór"}
            </button>
          </div>
        </>
      ) : (
        <>
          <ul className="space-y-3">
            {items.map((row) => (
              <li
                key={row.id}
                className="card space-y-3 [overflow-wrap:anywhere]"
              >
                <div className="flex items-start justify-between gap-3">
                  <h2 className="font-semibold">{row.description}</h2>
                  <span className="shrink-0 tabular-nums">
                    {row.amount_minor === null
                      ? "Kwota niedostępna"
                      : `${formatPLN(row.amount_minor)} zł`}
                  </span>
                </div>
                <p className="text-sm">
                  {partsLabel(row.current_parts)} →{" "}
                  <strong>
                    {row.target_path ??
                      row.new_category?.name ??
                      "Sprawdź ręcznie"}
                  </strong>
                </p>
                <p className="text-sm text-gray-400">{row.explanation}</p>
                <p className="text-xs text-gray-400">
                  Pewność modelu: {row.confidence}. Wymaga Twojego przeglądu.
                </p>
                {row.eligible ? (
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      aria-label={`Wybierz ${row.description}`}
                      checked={selected.includes(row.id)}
                      disabled={
                        busy ||
                        !active ||
                        (!selected.includes(row.id) &&
                          selected.length >= maxItems)
                      }
                      onChange={(e) =>
                        setSelected((s) =>
                          e.target.checked
                            ? [...s, row.id]
                            : s.filter((id) => id !== row.id),
                        )
                      }
                    />
                    Wybierz do przeglądu
                  </label>
                ) : (
                  <p className="text-sm text-amber-400">
                    {row.decision === "new_category"
                      ? "Nowa kategoria wymaga osobnego utworzenia i osobnego przypisania."
                      : "Propozycja nieaktualna lub chroniona — sprawdź ręcznie."}
                  </p>
                )}
                {row.new_category ? (
                  <p className="text-sm">
                    {row.new_category.parent_path
                      ? `Rodzic: ${row.new_category.parent_path}. `
                      : ""}
                    {row.new_category.explanation}{" "}
                    <Link
                      className="underline"
                      to="/settings/finances/categories"
                    >
                      Utwórz kategorię osobno
                    </Link>
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  {row.transaction_id ? (
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busy || !active}
                      onClick={() => setManual(row.transaction_id)}
                    >
                      Przypisz ręcznie
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={busy || !active}
                    onClick={() => void dismiss(row)}
                  >
                    {rejectUnknown === row.id
                      ? "Ponów odrzucenie"
                      : "Odrzuć propozycję"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="btn-primary"
            disabled={!selected.length || busy || !active}
            onClick={() => void prepare()}
          >
            Przejrzyj wybrane ({selected.length})
          </button>
        </>
      )}
      {!review ? (
        <div className="flex gap-3">
          {onFirstPage ? (
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => {
                setSelected([]);
                onFirstPage();
              }}
            >
              Pierwsza strona
            </button>
          ) : null}
          {onNextPage ? (
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => {
                setSelected([]);
                onNextPage();
              }}
            >
              Następna strona
            </button>
          ) : null}
        </div>
      ) : null}
      {manual && active ? (
        <TransactionCategorizationDialog
          id={manual}
          onClose={() => setManual(null)}
        />
      ) : null}
    </section>
  );
}
