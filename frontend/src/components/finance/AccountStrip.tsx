import { Link, useSearchParams } from "react-router-dom";
import { useAccounts, type Account } from "../../api/finance";
import { colorInk, entityColor } from "../../lib/financeColors";
import { formatPLN } from "../../lib/format";
import { QueryFeedback } from "../QueryFeedback";

function AccountContent({ account }: { account: Account }) {
  const color = entityColor(account.id, account.color);
  const balance =
    account.balance_source !== undefined
      ? `${formatPLN(account.balance_source)} ${account.currency}`
      : `${formatPLN(account.balance_pln)} PLN${account.currency === "PLN" ? "" : " · wartość księgowa"}`;
  return (
    <>
      <span
        className="finance-bank-mark"
        aria-hidden="true"
        style={{ backgroundColor: color, color: colorInk(color) }}
      >
        {(account.bank_name || account.name).slice(0, 1).toUpperCase()}
      </span>
      <span>
        <small>
          {account.bank_name
            ? `${account.bank_name} · ${account.name}`
            : account.name}
        </small>
        <strong>{balance}</strong>
        {account.currency !== "PLN" && account.balance_source !== undefined && (
          <small>Wartość księgowa: {formatPLN(account.balance_pln)} PLN</small>
        )}
      </span>
    </>
  );
}

export function AccountStrip({
  mode,
  periodSearch = "",
}: {
  mode: "filter" | "links";
  periodSearch?: string;
}) {
  const [search, setSearch] = useSearchParams();
  const accounts = useAccounts();
  const active = (accounts.data ?? []).filter(
    (account) => account.is_active !== false,
  );
  function toggle(id: string) {
    const next = new URLSearchParams(search);
    if (next.get("account_id") === id) next.delete("account_id");
    else next.set("account_id", id);
    next.delete("page");
    next.delete("detail");
    setSearch(next, { preventScrollReset: true });
  }
  return (
    <section className="my-6" aria-label="Twoje konta">
      <QueryFeedback
        loading={accounts.isLoading}
        error={accounts.isError}
        errorMessage="Nie udało się pobrać kont."
        onRetry={accounts.refetch}
      >
        <div className="finance-account-strip">
          {active.map((account) =>
            mode === "links" ? (
              <Link
                key={account.id}
                to={`/finances/transactions${periodSearch}${periodSearch ? "&" : "?"}account_id=${encodeURIComponent(account.id)}`}
                className="finance-account-chip"
                style={{ borderColor: entityColor(account.id, account.color) }}
              >
                <AccountContent account={account} />
              </Link>
            ) : (
              <button
                key={account.id}
                type="button"
                className="finance-account-chip finance-account-filter"
                style={{ borderColor: entityColor(account.id, account.color) }}
                aria-pressed={search.get("account_id") === account.id}
                onClick={() => toggle(account.id)}
              >
                <AccountContent account={account} />
              </button>
            ),
          )}
        </div>
        {active.length === 0 && (
          <div className="space-y-2 text-sm">
            <p className="text-gray-500">Brak aktywnych kont.</p>
            <Link
              className="inline-block underline"
              to="/settings/finances/accounts#new-account"
            >
              Dodaj konto
            </Link>
          </div>
        )}
      </QueryFeedback>
    </section>
  );
}
