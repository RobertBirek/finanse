import { useRef, useState } from "react";
import {
  useReceiptStores,
  useCreateReceiptStore,
} from "../../../api/receiptItems";
import type { ReceiptStore } from "../../../api/receiptItems";
import { useAuthStore } from "../../../stores/authStore";
import type { AxiosError } from "axios";

export function ReceiptStorePicker({
  storeId,
  disabled,
  maxName,
  onChange,
  onBusyChange,
}: {
  storeId: string | null;
  disabled: boolean;
  maxName: number;
  onChange: (store: ReceiptStore) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const stores = useReceiptStores(null, true),
    create = useCreateReceiptStore();
  const [query, setQuery] = useState(""),
    [name, setName] = useState(""),
    [failure, setFailure] = useState<string | null>(null),
    [unknown, setUnknown] = useState(false);
  const intent = useRef<{
      session: number;
      key: string;
      body: Record<string, unknown>;
    } | null>(null),
    busy = useRef(false);
  const all = stores.data?.pages.flatMap((p) => p.items) ?? [];
  async function save() {
    if (
      disabled ||
      busy.current ||
      session !== useAuthStore.getState().sessionVersion
    )
      return;
    const input = intent.current ?? {
      session,
      key: crypto.randomUUID(),
      body: { name },
    };
    intent.current = input;
    busy.current = true;
    onBusyChange(true);
    try {
      const store = await create.mutateAsync(input);
      if (session === useAuthStore.getState().sessionVersion) {
        onChange(store);
        intent.current = null;
        setName("");
        setUnknown(false);
        setFailure(null);
        onBusyChange(false);
      }
    } catch (error) {
      if (session === useAuthStore.getState().sessionVersion) {
        const status = (error as AxiosError).response?.status;
        const uncertain = !status || status >= 500;
        setUnknown(uncertain);
        setFailure(
          uncertain
            ? "Wynik utworzenia sklepu nieznany. Ponów z tym samym kluczem."
            : "Nie udało się utworzyć sklepu. Sprawdź nazwę i aktualną listę.",
        );
        if (!uncertain) {
          intent.current = null;
          onBusyChange(false);
        }
      }
    } finally {
      busy.current = false;
    }
  }
  return (
    <section className="space-y-2" aria-label="Sklep paragonu">
      <label className="block text-sm">
        Szukaj sklepu
        <input
          className="input mt-1"
          value={query}
          disabled={disabled || unknown || create.isPending}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <label className="block text-sm">
        Sklep
        <select
          className="input mt-1"
          value={all.some((s) => s.id === storeId) ? (storeId ?? "") : ""}
          disabled={disabled || unknown || create.isPending}
          onChange={(e) => {
            const store = all.find((s) => s.id === e.target.value);
            if (store) onChange(store);
          }}
        >
          <option value="">Wybierz sklep</option>
          {all
            .filter(
              (s) =>
                s.id === storeId ||
                s.name
                  .toLocaleLowerCase("pl")
                  .includes(query.toLocaleLowerCase("pl")),
            )
            .map((s) => (
              <option key={s.id} value={s.id} disabled={!s.active}>
                {s.name}
                {!s.active ? " (archiwalny)" : ""}
              </option>
            ))}
        </select>
      </label>
      {stores.isError ? (
        <p role="alert">
          Nie udało się pobrać sklepów.{" "}
          <button type="button" onClick={() => void stores.refetch()}>
            Ponów listę
          </button>
        </p>
      ) : null}
      {stores.hasNextPage ? (
        <button
          type="button"
          className="btn-secondary"
          disabled={disabled || stores.isFetchingNextPage}
          onClick={() => void stores.fetchNextPage()}
        >
          Wczytaj kolejne sklepy
        </button>
      ) : null}
      <label className="block text-sm">
        Nowy sklep
        <input
          className="input mt-1"
          value={name}
          maxLength={maxName}
          disabled={disabled || unknown || create.isPending}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <button
        type="button"
        className="btn-secondary"
        disabled={disabled || create.isPending || (!unknown && !name.trim())}
        onClick={() => void save()}
      >
        {unknown ? "Ponów utworzenie sklepu" : "Utwórz własny sklep"}
      </button>
      {failure ? (
        <p role="alert" className="text-sm">
          {failure}
        </p>
      ) : null}
      {unknown ? (
        <button
          type="button"
          className="btn-secondary"
          disabled={disabled || create.isPending}
          onClick={() => {
            intent.current = null;
            setUnknown(false);
            setFailure(
              "Sklep mógł już powstać. Sprawdź listę przed kolejną próbą.",
            );
            onBusyChange(false);
            void stores.refetch();
          }}
        >
          Porzuć próbę i sprawdź listę sklepów
        </button>
      ) : null}
    </section>
  );
}
