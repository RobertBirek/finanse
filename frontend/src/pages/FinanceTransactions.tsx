import { TransactionSearch } from "../components/finance/TransactionSearch";
import { TransactionForm } from "../components/finance/TransactionForm";

export function FinanceTransactions() {
  return (
    <div className="max-w-6xl space-y-6">
      <h1 className="text-2xl font-bold text-white">Transakcje</h1>
      <TransactionSearch />
      <details className="card">
        <summary className="cursor-pointer text-lg font-semibold text-white">
          Dodaj transakcję
        </summary>
        <div className="mt-4">
          <TransactionForm />
        </div>
      </details>
    </div>
  );
}
