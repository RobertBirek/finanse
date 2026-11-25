import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAccounts, useBalanceReconciliation } from "../../api/finance";

import { parseStatementBalance } from "../../lib/statementBalance";

function formatBalance(minor: string, currency: string): string {
  const value = BigInt(minor);
  const abs = value < 0n ? -value : value;
  return `${value < 0n ? "−" : ""}${(abs / 100n).toLocaleString("pl-PL")},${String(abs % 100n).padStart(2, "0")} ${currency}`;
}

export function BalanceReconciliation({
  onHistory,
}: {
  onHistory: () => void;
}) {
  const { data: accounts, isLoading, isError } = useAccounts();
  const check = useBalanceReconciliation();
  const [account, setAccount] = useState("");
  const [day, setDay] = useState("");
  const [balance, setBalance] = useState("");
  const [invalid, setInvalid] = useState(false);
  const selected = accounts?.find(({ id }) => id === account);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !day || check.isPending) return;
    const minor = parseStatementBalance(balance);
    setInvalid(minor === null);
    if (minor === null) {
      check.reset();
      return;
    }
    check.mutate({ account, day, statement_minor: minor });
  }

  const result = check.data;
  return (
    <form className="mt-4 space-y-4" onSubmit={submit}>
      <p>
        Porównaj saldo końcowe z wyciągu z zaksięgowanymi operacjami. Niczego
        nie zapisujemy.
      </p>
      <fieldset className="space-y-3" disabled={check.isPending}>
        <label className="block">
          Konto
          <select
            className="input mt-1"
            required
            value={account}
            onChange={(event) => {
              setAccount(event.target.value);
              check.reset();
            }}
          >
            <option value="">Wybierz konto</option>
            {accounts?.map(({ id, name, currency }) => (
              <option key={id} value={id}>
                {name} ({currency})
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          Data końcowa wyciągu
          <input
            className="input mt-1"
            required
            type="date"
            value={day}
            onChange={(event) => {
              setDay(event.target.value);
              check.reset();
            }}
          />
        </label>
        <label className="block">
          Saldo końcowe z wyciągu{selected ? ` (${selected.currency})` : ""}
          <input
            className="input mt-1"
            required
            inputMode="decimal"
            value={balance}
            onChange={(event) => {
              setBalance(event.target.value);
              setInvalid(false);
              check.reset();
            }}
          />
        </label>
        <button
          className="btn-primary"
          type="submit"
          disabled={!selected || isLoading}
        >
          Porównaj salda
        </button>
      </fieldset>
      {isError && <p role="alert">Nie udało się pobrać kont.</p>}
      {invalid && (
        <p role="alert">
          Podaj poprawną kwotę z maksymalnie dwoma miejscami po przecinku.
        </p>
      )}
      {check.isError && (
        <p role="alert">Nie udało się porównać sald. Spróbuj ponownie.</p>
      )}
      {result && (
        <section role="status" className="space-y-2">
          <p>
            Saldo księgowe:{" "}
            {formatBalance(result.ledger_minor, result.currency)}
          </p>
          <p>
            Saldo z wyciągu:{" "}
            {formatBalance(result.statement_minor, result.currency)}
          </p>
          {result.difference_minor === "0" ? (
            <p>Salda są zgodne.</p>
          ) : (
            <>
              <p>
                Różnica (wyciąg minus księga):{" "}
                {formatBalance(result.difference_minor, result.currency)}
              </p>
              <Link
                className="underline"
                onClick={onHistory}
                to={`/finances/transactions?${new URLSearchParams({
                  account_id: account,
                  date_to: result.day,
                  date_basis: "booking",
                })}`}
              >
                Przejdź do historii konta
              </Link>
            </>
          )}
        </section>
      )}
    </form>
  );
}
