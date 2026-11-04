import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useReceiptHistory } from "../../../api/receiptItems";
import type {
  ReceiptHistoryPage,
  ReceiptHistoryRef,
} from "../../../api/receiptItems";
import { useAuthStore } from "../../../stores/authStore";
export function ReceiptHistoryHints({
  billId,
  storeId,
  name,
  categoryId,
  disabled,
  onChoose,
}: {
  billId: string;
  storeId: string | null;
  name: string;
  categoryId: string | null;
  disabled: boolean;
  onChoose: (ref: ReceiptHistoryRef) => void;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const query = useReceiptHistory();
  const [result, setResult] = useState<{
    generation: number;
    data: ReceiptHistoryPage;
  } | null>(null);
  const [error, setError] = useState<{
    generation: number;
    message: string;
  } | null>(null);
  const scope = JSON.stringify([billId, storeId, name, categoryId]);
  const current = useRef({ scope, generation: 0 });
  if (current.current.scope !== scope)
    current.current = { scope, generation: current.current.generation + 1 };
  const alive = useRef(true),
    abort = useRef<AbortController | null>(null);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      abort.current?.abort();
    };
  }, []);
  const active = () =>
    alive.current && session === useAuthStore.getState().sessionVersion;
  async function fetchHistory() {
    if (!storeId || !name.trim() || !active() || query.isPending) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    const generation = current.current.generation;
    try {
      const data = await query.mutateAsync({
        session,
        billId,
        storeId,
        name,
        signal: controller.signal,
      });
      if (active() && current.current.generation === generation) {
        setResult({ generation, data });
        setError(null);
      }
    } catch {
      if (active() && current.current.generation === generation)
        setError({
          generation,
          message:
            "Nie udało się pobrać historii. Wybierz kategorię z listy lub spróbuj ponownie.",
        });
    }
  }
  const data =
    result?.generation === current.current.generation ? result.data : null;
  return (
    <div className="space-y-2 text-sm">
      <button
        type="button"
        className="btn-secondary"
        disabled={disabled || !storeId || !name.trim() || query.isPending}
        onClick={() => void fetchHistory()}
      >
        Sprawdź historię sklepu
      </button>
      {error?.generation === current.current.generation ? (
        <p role="alert">{error.message}</p>
      ) : null}
      {data ? (
        <>
          {data.history_incomplete || data.has_more ? (
            <p>
              Historia jest niepełna — pokazujemy ograniczoną liczbę wskazówek.
            </p>
          ) : null}
          {data.conflict ? (
            <p>Ten produkt miał różne kategorie. Wybierz świadomie.</p>
          ) : null}
          {!data.items.length ? (
            <p>
              Brak wskazówki w sprawdzonej historii. Wybierz kategorię z pełnej
              listy.
            </p>
          ) : null}
          <ul className="space-y-2">
            {data.items.map((h) => (
              <li
                key={`${h.ref.source_revision_id}:${h.ref.source_line_key}`}
                className="rounded border border-gray-700 p-2 [overflow-wrap:anywhere]"
              >
                <p>
                  {h.product_name} → {h.category_path}
                </p>
                <p className="text-xs text-gray-400">
                  {h.ref.match_kind === "prefix"
                    ? "Przybliżona nazwa"
                    : "Ta sama nazwa"}{" "}
                  · {h.purchased_on ?? "Data zakupu nieznana"} ·{" "}
                  <Link
                    className="underline"
                    to={`/finances/documents?bill=${h.ref.source_bill_id}`}
                  >
                    Paragon źródłowy
                  </Link>
                </p>
                <button
                  type="button"
                  className="btn-secondary mt-2"
                  disabled={disabled}
                  onClick={() => {
                    if (
                      active() &&
                      result?.generation === current.current.generation
                    )
                      onChoose(h.ref);
                  }}
                >
                  Użyj kategorii
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
