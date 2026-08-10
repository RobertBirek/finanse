import { useState } from "react";
import {
  useAccounts,
  useCreateAccount,
  useTransactions,
  useCreateTransaction,
  useFinancialSummary,
  useCategories,
} from "../api/finance";

interface PostingForm {
  account_id: string;
  source_amount: string;
  direction: "debit" | "credit";
}

export function Finances() {
  const { data: accounts } = useAccounts();
  const { data: transactions, isLoading: txLoading } = useTransactions({ limit: 50 });
  const { data: summary } = useFinancialSummary();
  const createTx = useCreateTransaction();

  const [showTxForm, setShowTxForm] = useState(false);
  const [txDesc, setTxDesc] = useState("");
  const [txType, setTxType] = useState("expense");
  const [postings, setPostings] = useState<PostingForm[]>([
    { account_id: "", source_amount: "", direction: "debit" },
    { account_id: "", source_amount: "", direction: "credit" },
  ]);

  const totalBalance = accounts?.reduce(
    (sum, a) => sum + 0 /* server calculated */,
    0
  ) || 0;

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
        <button onClick={() => setShowTxForm(true)} className="btn-primary">
          + Nowa transakcja
        </button>
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
              <p className="text-sm font-mono text-gray-300">
                — {account.currency}
              </p>
            </div>
          ))}
        </div>
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
          <p className="text-gray-500 text-sm">Brak transakcji</p>
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
                      {p.direction === "debit" ? "DEBIT" : "CREDIT"}
                    </span>
                    <select
                      value={p.direction}
                      onChange={(e) =>
                        updatePosting(i, "direction", e.target.value)
                      }
                      className="input text-xs w-24"
                    >
                      <option value="debit">Przychód</option>
                      <option value="credit">Wydatek</option>
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
