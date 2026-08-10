import { useState } from "react";
import {
  useAccounts,
  useCreateAccount,
  useTransactions,
  useCreateTransaction,
  useFinancialSummary,
} from "../api/finance";

interface PostingForm {
  account_id: string;
  source_amount: string;
  direction: "debit" | "credit";
}

const SUGGESTED_ACCOUNTS = [
  { name: "ING PLN", type: "checking" },
  { name: "Revolut PLN", type: "checking" },
  { name: "Revolut EUR", type: "checking" },
  { name: "Gotówka PLN", type: "cash" },
  { name: "Oszczędności", type: "savings" },
];

export function Finances() {
  const { data: accounts } = useAccounts();
  const createAccount = useCreateAccount();
  const { data: transactions, isLoading: txLoading } = useTransactions({ limit: 50 });
  const { data: summary } = useFinancialSummary();
  const createTx = useCreateTransaction();

  const [showTxForm, setShowTxForm] = useState(false);
  const [showAccountForm, setShowAccountForm] = useState(false);
  const [newAccountName, setNewAccountName] = useState("");
  const [newAccountType, setNewAccountType] = useState("checking");
  const [newAccountCurrency, setNewAccountCurrency] = useState("PLN");

  const [txDesc, setTxDesc] = useState("");
  const [txType, setTxType] = useState("expense");
  const [postings, setPostings] = useState<PostingForm[]>([
    { account_id: "", source_amount: "", direction: "debit" },
    { account_id: "", source_amount: "", direction: "credit" },
  ]);

  const handleCreateAccount = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAccountName.trim()) return;
    createAccount.mutate(
      { name: newAccountName.trim(), type: newAccountType, currency: newAccountCurrency },
      {
        onSuccess: () => {
          setNewAccountName("");
          setShowAccountForm(false);
        },
      }
    );
  };

  const handleTxSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!txDesc.trim()) return;

    const validPostings = postings.filter(
      (p) => p.account_id && p.source_amount
    );
    if (validPostings.length < 2) return;

    createTx.mutate(
      {
        description: txDesc.trim(),
        type: txType,
        postings: validPostings.map((p) => ({
          account_id: p.account_id,
          source_amount: Math.round(parseFloat(p.source_amount) * 100),
          base_amount_pln: Math.round(parseFloat(p.source_amount) * 100),
          direction: p.direction,
        })),
      },
      {
        onSuccess: () => {
          setTxDesc("");
          setPostings([
            { account_id: "", source_amount: "", direction: "debit" },
            { account_id: "", source_amount: "", direction: "credit" },
          ]);
          setShowTxForm(false);
        },
      }
    );
  };

  const updatePosting = (idx: number, field: string, value: string) => {
    setPostings((prev) =>
      prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p))
    );
  };

  const formatPLN = (amount: number) => {
    return new Intl.NumberFormat("pl-PL", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount / 100);
  };

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Finanse</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowAccountForm(true)} className="btn-secondary">
            + Konto
          </button>
          <button onClick={() => setShowTxForm(true)} className="btn-primary">
            + Transakcja
          </button>
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Przychody</p>
            <p className="text-lg font-bold text-green-400">
              {formatPLN(summary.income_total_pln)} PLN
            </p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Wydatki</p>
            <p className="text-lg font-bold text-red-400">
              {formatPLN(summary.expense_total_pln)} PLN
            </p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Bilans</p>
            <p
              className={`text-lg font-bold ${
                summary.net_total_pln >= 0 ? "text-green-400" : "text-red-400"
              }`}
            >
              {formatPLN(summary.net_total_pln)} PLN
            </p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-400 mb-1">Okres</p>
            <p className="text-lg font-bold text-gray-200">
              {summary.month}.{summary.year}
            </p>
          </div>
        </div>
      )}

      {/* Accounts list */}
      <div className="card mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">Konta</h2>
        {accounts?.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-500">Brak kont</p>
            <p className="text-gray-600 text-sm mt-1">
              Dodaj pierwsze konto, aby rozpocząć
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {accounts?.map((account) => (
              <div
                key={account.id}
                className="flex items-center justify-between p-3 rounded-lg bg-gray-800/50"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      account.is_active ? "bg-green-400" : "bg-gray-600"
                    }`}
                  />
                  <div>
                    <p className="text-sm font-medium text-white">{account.name}</p>
                    <p className="text-xs text-gray-500">
                      {account.type} · {account.currency}
                    </p>
                  </div>
                </div>
                <p className={`text-sm font-mono font-medium ${(account.balance_pln ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {formatPLN(account.balance_pln ?? 0)} {account.currency}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent transactions */}
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">
          Ostatnie transakcje
        </h2>
        {txLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-6 h-6 border-2 border-advisor-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : transactions?.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-500">Brak transakcji</p>
            <p className="text-gray-600 text-sm mt-1">
              Dodaj pierwszą transakcję
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {transactions?.map((tx) => (
              <div
                key={tx.id}
                className="flex items-center justify-between p-3 rounded-lg bg-gray-800/50"
              >
                <div>
                  <p className="text-sm text-gray-200">{tx.description}</p>
                  <p className="text-xs text-gray-500">
                    {new Date(tx.transaction_date).toLocaleDateString("pl-PL")} · {tx.type}
                    {tx.is_pending && " · Oczekuje"}
                  </p>
                </div>
                <div className="text-right">
                  {tx.postings?.map((p) => (
                    <p
                      key={p.id}
                      className={`text-sm font-mono ${
                        p.direction === "debit"
                          ? "text-green-400"
                          : "text-red-400"
                      }`}
                    >
                      {p.direction === "debit" ? "+" : "−"}
                      {formatPLN(p.base_amount_pln)} PLN
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Account creation modal */}
      {showAccountForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="card w-full max-w-sm">
            <h2 className="text-lg font-semibold text-white mb-4">Nowe konto</h2>
            <form onSubmit={handleCreateAccount} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Nazwa</label>
                <input
                  value={newAccountName}
                  onChange={(e) => setNewAccountName(e.target.value)}
                  className="input"
                  placeholder="np. ING PLN"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Typ</label>
                <select
                  value={newAccountType}
                  onChange={(e) => setNewAccountType(e.target.value)}
                  className="input"
                >
                  <option value="checking">Konto bieżące</option>
                  <option value="savings">Oszczędnościowe</option>
                  <option value="cash">Gotówka</option>
                  <option value="credit">Karta kredytowa</option>
                  <option value="investment">Inwestycyjne</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Waluta</label>
                <select
                  value={newAccountCurrency}
                  onChange={(e) => setNewAccountCurrency(e.target.value)}
                  className="input"
                >
                  <option value="PLN">PLN</option>
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </div>
              <div className="text-xs text-gray-600">
                <p className="mb-1">Szybki wybór:</p>
                <div className="flex flex-wrap gap-1">
                  {SUGGESTED_ACCOUNTS.map((acc) => (
                    <button
                      key={acc.name}
                      type="button"
                      onClick={() => {
                        setNewAccountName(acc.name);
                        setNewAccountType(acc.type);
                        setNewAccountCurrency(
                          acc.name.includes("EUR") ? "EUR" : "PLN"
                        );
                      }}
                      className="px-2 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-400"
                    >
                      {acc.name}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex gap-3 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setShowAccountForm(false)}
                  className="btn-secondary"
                >
                  Anuluj
                </button>
                <button
                  type="submit"
                  disabled={createAccount.isPending || !newAccountName.trim()}
                  className="btn-primary"
                >
                  {createAccount.isPending ? "..." : "Dodaj"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Transaction form modal */}
      {showTxForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="card w-full max-w-lg">
            <h2 className="text-lg font-semibold text-white mb-4">
              Nowa transakcja
            </h2>
            <form onSubmit={handleTxSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Opis</label>
                <input
                  value={txDesc}
                  onChange={(e) => setTxDesc(e.target.value)}
                  className="input"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Typ</label>
                <select
                  value={txType}
                  onChange={(e) => setTxType(e.target.value)}
                  className="input"
                >
                  <option value="expense">Wydatek</option>
                  <option value="income">Przychód</option>
                  <option value="transfer">Transfer</option>
                  <option value="exchange">Przewalutowanie</option>
                </select>
              </div>

              {postings.map((p, i) => (
                <div key={i} className="p-3 rounded-lg bg-gray-800/50 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 w-16">
                      {i === 0 ? "Z konta" : "Na konto/kategorię"}
                    </span>
                    <select
                      value={p.direction}
                      onChange={(e) =>
                        updatePosting(i, "direction", e.target.value)
                      }
                      className="input text-xs w-24"
                    >
                      <option value="debit">DEBIT</option>
                      <option value="credit">CREDIT</option>
                    </select>
                  </div>
                  <select
                    value={p.account_id}
                    onChange={(e) =>
                      updatePosting(i, "account_id", e.target.value)
                    }
                    className="input"
                    required
                  >
                    <option value="">Wybierz konto</option>
                    {accounts?.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.currency})
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="Kwota (PLN)"
                    value={p.source_amount}
                    onChange={(e) =>
                      updatePosting(i, "source_amount", e.target.value)
                    }
                    className="input"
                    required
                  />
                </div>
              ))}

              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setShowTxForm(false)}
                  className="btn-secondary"
                >
                  Anuluj
                </button>
                <button
                  type="submit"
                  disabled={createTx.isPending}
                  className="btn-primary"
                >
                  {createTx.isPending ? "Zapisywanie..." : "Zapisz"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
