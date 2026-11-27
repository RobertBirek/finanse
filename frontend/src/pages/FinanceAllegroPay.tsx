import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  useAccounts,
  useCategories,
  useTransactionSearch,
  parsePlnToGrosze,
} from "../api/finance";
import {
  useAllegroPay,
  useAllegroPayCommand,
  useUnlinkAllegroPayment,
  type AllegroProfile,
} from "../api/allegroPay";
import { PageHeader } from "../components/PageHeader";
import { formatPLN } from "../lib/format";
import { formatCalendarDate } from "../lib/date";
import { loanApiErrorMessage } from "../api/loans";

type Row = {
  due_date: string;
  principal: string;
  interest: string;
  fees: string;
};
const emptyRow = (): Row => ({
  due_date: "",
  principal: "",
  interest: "0",
  fees: "0",
});

function TransactionPicker({
  accountId,
  type,
  value,
  onChange,
}: {
  accountId: string;
  type: "expense" | "transfer";
  value: string;
  onChange: (value: string) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const results = useTransactionSearch({
    account_id: accountId,
    type,
    q: query || undefined,
    limit: 50,
    offset,
  });
  const items = results.data?.items ?? [];
  return (
    <div className="space-y-2">
      <label>
        Wyszukaj transakcję
        <input
          className="input"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOffset(0);
            onChange("");
          }}
        />
      </label>
      <label>
        {type === "expense" ? "Transakcja" : "Istniejący przelew"}
        <select
          required
          className="input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">
            {type === "expense"
              ? "Wybierz wydatek"
              : "Wybierz przelew na konto Allegro Pay"}
          </option>
          {items
            .filter((item) => !item.is_pending)
            .map((item) => {
              const posting = item.postings.find(
                (entry) => entry.account_id === accountId,
              );
              return (
                <option key={item.id} value={item.id}>
                  {item.transaction_date} · {item.description} ·{" "}
                  {posting
                    ? `${formatPLN(posting.base_amount_pln)} PLN`
                    : item.id}
                </option>
              );
            })}
        </select>
      </label>
      {results.isError ? (
        <p role="alert">Nie udało się pobrać transakcji.</p>
      ) : null}
      <div className="flex gap-2 text-sm">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => {
            setOffset(Math.max(0, offset - 50));
            onChange("");
          }}
        >
          Poprzednie
        </button>
        <span>
          {results.isLoading
            ? "Ładowanie…"
            : `Transakcje ${Math.min(offset + 1, results.data?.total ?? 0)}–${Math.min(offset + 50, results.data?.total ?? 0)} z ${results.data?.total ?? 0}`}
        </span>
        <button
          type="button"
          disabled={offset + 50 >= (results.data?.total ?? 0)}
          onClick={() => {
            setOffset(offset + 50);
            onChange("");
          }}
        >
          Następne
        </button>
      </div>
    </div>
  );
}

function PurchaseForm({ profile }: { profile: AllegroProfile }) {
  const categories = useCategories();
  const create = useAllegroPayCommand(`/${profile.id}/purchases`, "post");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [principal, setPrincipal] = useState("");
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [selected, setSelected] = useState("");
  const [category, setCategory] = useState("");
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [error, setError] = useState("");
  function update(index: number, key: keyof Row, value: string) {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, [key]: value } : row)),
    );
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const amount = parsePlnToGrosze(principal);
    const installments = rows.map((row) => ({
      due_date: row.due_date,
      principal_pln: parsePlnToGrosze(row.principal, true),
      interest_pln: parsePlnToGrosze(row.interest, true),
      fees_pln: parsePlnToGrosze(row.fees, true),
    }));
    if (
      !amount ||
      installments.some(
        (r) =>
          !r.due_date ||
          r.principal_pln === null ||
          r.interest_pln === null ||
          r.fees_pln === null,
      )
    ) {
      setError("Sprawdź kwotę i wszystkie pola rat.");
      return;
    }
    setError("");
    try {
      await create.mutateAsync({
        request_id: requestId,
        name,
        purchase_date: date,
        principal_pln: amount,
        transaction_id: mode === "existing" ? selected : null,
        category_id: mode === "new" ? category : null,
        installments,
      });
      setName("");
      setDate("");
      setPrincipal("");
      setSelected("");
      setRows([emptyRow()]);
      setRequestId(crypto.randomUUID());
    } catch (reason) {
      setError(loanApiErrorMessage(reason) ?? "Nie udało się zapisać zakupu.");
    }
  }
  return (
    <form aria-label="Dodaj zakup" className="card space-y-3" onSubmit={submit}>
      <h2 className="text-lg font-semibold">Dodaj zakup</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <label>
          Nazwa
          <input
            required
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Data zakupu
          <input
            required
            type="date"
            className="input"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <label>
          Kwota zakupu PLN
          <input
            required
            className="input"
            inputMode="decimal"
            value={principal}
            onChange={(e) => setPrincipal(e.target.value)}
          />
        </label>
      </div>
      <label>
        Wydatek
        <select
          className="input"
          value={mode}
          onChange={(e) => setMode(e.target.value as "existing" | "new")}
        >
          <option value="existing">Powiąż istniejący</option>
          <option value="new">Utwórz nowy</option>
        </select>
      </label>
      {mode === "existing" ? (
        <TransactionPicker
          accountId={profile.account_id}
          type="expense"
          value={selected}
          onChange={setSelected}
        />
      ) : (
        <label>
          Kategoria
          <select
            required
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">Wybierz kategorię</option>
            {(categories.data ?? [])
              .filter((c) => c.is_active && c.type === "expense")
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </label>
      )}
      <h3 className="font-semibold">Harmonogram spłat</h3>
      {rows.map((row, index) => (
        <fieldset key={index} className="grid gap-2 sm:grid-cols-4">
          <legend>Rata {index + 1}</legend>
          <label>
            Termin
            <input
              required
              type="date"
              className="input"
              value={row.due_date}
              onChange={(e) => update(index, "due_date", e.target.value)}
            />
          </label>
          <label>
            Kapitał PLN
            <input
              required
              className="input"
              inputMode="decimal"
              value={row.principal}
              onChange={(e) => update(index, "principal", e.target.value)}
            />
          </label>
          <label>
            Odsetki PLN
            <input
              required
              className="input"
              inputMode="decimal"
              value={row.interest}
              onChange={(e) => update(index, "interest", e.target.value)}
            />
          </label>
          <label>
            Opłaty PLN
            <input
              required
              className="input"
              inputMode="decimal"
              value={row.fees}
              onChange={(e) => update(index, "fees", e.target.value)}
            />
          </label>
        </fieldset>
      ))}
      <div className="flex gap-2">
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setRows([...rows, emptyRow()])}
        >
          Dodaj ratę
        </button>
        {rows.length > 1 ? (
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setRows(rows.slice(0, -1))}
          >
            Usuń ostatnią ratę
          </button>
        ) : null}
        <button className="btn-primary" disabled={create.isPending}>
          Zapisz zakup
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </form>
  );
}

export function AllegroPayDetails({ profile }: { profile: AllegroProfile }) {
  const payment = useAllegroPayCommand(`/${profile.id}/payments`, "post");
  const unlink = useUnlinkAllegroPayment(profile.id);
  const [transaction, setTransaction] = useState("");
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const installments = profile.purchases
    .flatMap((purchase) =>
      purchase.installments.map((item) => ({
        ...item,
        purchaseName: purchase.name,
        purchaseDate: purchase.purchase_date,
        purchasePrincipal: purchase.principal_pln,
      })),
    )
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  async function submit(event: FormEvent) {
    event.preventDefault();
    const allocations = Object.entries(amounts)
      .filter(([, value]) => value.trim())
      .map(([installment_id, value]) => ({
        installment_id,
        amount_pln: parsePlnToGrosze(value),
      }));
    if (
      !allocations.length ||
      allocations.some((item) => item.amount_pln === null)
    ) {
      setError("Podaj kwoty przypisania do rat.");
      return;
    }
    try {
      await payment.mutateAsync({ transaction_id: transaction, allocations });
      setTransaction("");
      setAmounts({});
      setError("");
    } catch (reason) {
      setError(
        loanApiErrorMessage(reason) ?? "Nie udało się przypisać spłaty.",
      );
    }
  }
  return (
    <div className="space-y-4">
      <section className="card space-y-2">
        <h2 className="text-xl font-semibold">{profile.account_name}</h2>
        <p>
          Saldo księgowe {formatPLN(profile.ledger_balance_pln)} PLN · Limit{" "}
          {profile.limit_pln === null
            ? "nieustalony"
            : `${formatPLN(profile.limit_pln)} PLN`}{" "}
          · Dostępne według księgi{" "}
          {profile.available_pln === null
            ? "nieustalone"
            : `${formatPLN(profile.available_pln)} PLN`}
        </p>
        <p>
          Do pokrycia według harmonogramów{" "}
          {formatPLN(profile.scheduled_remaining_pln)} PLN · Planowane odsetki i
          opłaty {formatPLN(profile.scheduled_costs_pln)} PLN
        </p>
        <p>
          Różnica między zadłużeniem księgowym a pozostałymi ratami{" "}
          {formatPLN(
            -profile.ledger_balance_pln - profile.scheduled_remaining_pln,
          )}{" "}
          PLN
        </p>
        <p className="text-sm text-gray-400">
          Saldo księgowe i harmonogramy mają odrębne źródła. Sprawdź ich
          zgodność z panelem Allegro Pay. Planowane odsetki i opłaty nie są
          automatycznie księgowane. Gdy zostaną naliczone,{" "}
          <Link
            className="underline"
            to="/finances/transactions?create=expense"
          >
            dodaj je jako osobne wydatki
          </Link>{" "}
          na tym koncie, w odpowiednich kategoriach.
        </p>
      </section>
      <Link className="btn-secondary" to="/settings/finances/loans/allegro-pay">
        Ustawienia Allegro Pay
      </Link>
      <form
        aria-label="Zakupy i spłaty"
        className="card space-y-3"
        onSubmit={submit}
      >
        <h2 className="text-lg font-semibold">Zakupy i spłaty</h2>
        {installments.length === 0 ? <p>Brak wprowadzonych rat.</p> : null}
        {installments.map((item) => (
          <div key={item.id} className="border-t border-gray-700 py-3">
            <p>
              <strong>{item.purchaseName}</strong> · rata {item.number} ·{" "}
              {formatCalendarDate(item.due_date)}
            </p>
            <p className="text-sm">
              Zakup {formatCalendarDate(item.purchaseDate)} ·{" "}
              {formatPLN(item.purchasePrincipal)} PLN ·{" "}
              {item.remaining_pln === 0
                ? "Spłacona"
                : item.paid_pln > 0
                  ? "Częściowo spłacona"
                  : "Niespłacona"}
            </p>
            <p>
              Kapitał {formatPLN(item.principal_pln)} PLN · odsetki{" "}
              {formatPLN(item.interest_pln)} PLN · opłaty{" "}
              {formatPLN(item.fees_pln)} PLN
            </p>
            <p>
              Zapłacono {formatPLN(item.paid_pln)} PLN · pozostało{" "}
              {formatPLN(item.remaining_pln)} PLN
            </p>
            {item.payments.map((link) => (
              <p key={link.transaction_id} className="text-sm">
                Przelew {link.transaction_id} · {formatPLN(link.amount_pln)} PLN{" "}
                <button
                  type="button"
                  className="underline"
                  disabled={unlink.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        "Usunąć wszystkie przypisania tego przelewu do rat?",
                      )
                    ) {
                      unlink.mutate(link.transaction_id, {
                        onError: (reason) =>
                          setError(
                            loanApiErrorMessage(reason) ??
                              "Nie udało się odpiąć spłaty.",
                          ),
                      });
                    }
                  }}
                >
                  Odepnij przelew
                </button>
              </p>
            ))}
            {item.remaining_pln > 0 ? (
              <label>
                Przypisz do raty PLN
                <input
                  className="input"
                  inputMode="decimal"
                  value={amounts[item.id] ?? ""}
                  onChange={(e) =>
                    setAmounts({ ...amounts, [item.id]: e.target.value })
                  }
                />
              </label>
            ) : null}
          </div>
        ))}
        {installments.length ? (
          <>
            <TransactionPicker
              accountId={profile.account_id}
              type="transfer"
              value={transaction}
              onChange={setTransaction}
            />
            <button className="btn-primary" disabled={payment.isPending}>
              Przypisz spłatę
            </button>
          </>
        ) : null}
        {error ? <p role="alert">{error}</p> : null}
      </form>
    </div>
  );
}

export function FinanceAllegroPay() {
  const accounts = useAccounts();
  const profiles = useAllegroPay();
  const save = useAllegroPayCommand("", "put");
  const [account, setAccount] = useState("");
  const [limit, setLimit] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    const limitAmount = limit.trim() ? parsePlnToGrosze(limit) : null;
    if (limit.trim() && limitAmount === null) {
      setError("Sprawdź limit.");
      return;
    }
    try {
      await save.mutateAsync({ account_id: account, limit_pln: limitAmount });
      setError("");
    } catch (reason) {
      setError(loanApiErrorMessage(reason) ?? "Nie udało się zapisać konta.");
    }
  }
  return (
    <div className="page-workspace space-y-5">
      <PageHeader title="Allegro Pay" />
      <Link className="underline" to="/finances/loans">
        Wróć do kredytów i pożyczek
      </Link>
      {accounts.isError || profiles.isError ? (
        <p role="alert">Nie udało się pobrać danych. Odśwież stronę.</p>
      ) : null}
      {accounts.isLoading || profiles.isLoading ? (
        <p role="status">Ładowanie…</p>
      ) : null}
      <form
        aria-label="Konto i limit"
        className="card space-y-3"
        onSubmit={submit}
      >
        <h2 className="text-lg font-semibold">Konto i limit</h2>
        <label>
          Konto
          <select
            required
            className="input"
            value={account}
            onChange={(e) => {
              const selectedAccount = e.target.value;
              const existing = profiles.data?.find(
                (profile) => profile.account_id === selectedAccount,
              );
              setAccount(selectedAccount);
              setLimit(
                existing?.limit_pln != null
                  ? String(existing.limit_pln / 100)
                  : "",
              );
            }}
          >
            <option value="">Wybierz konto</option>
            {(accounts.data ?? [])
              .filter(
                (a) => a.is_active && a.currency === "PLN" && !a.credit_card,
              )
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          Limit PLN
          <input
            className="input"
            inputMode="decimal"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
        <button className="btn-primary" disabled={save.isPending}>
          Zapisz konto
        </button>
        {error ? <p role="alert">{error}</p> : null}
      </form>
      {(profiles.data ?? []).map((profile) => (
        <section key={profile.id} className="space-y-2">
          <Link
            className="underline"
            to={`/finances/loans?allegro=${encodeURIComponent(profile.id)}`}
          >
            Otwórz spłaty · {profile.account_name}
          </Link>
          <PurchaseForm profile={profile} />
        </section>
      ))}
    </div>
  );
}
