import { useAccounts } from "../api/finance";
import { AccountTransactions } from "../components/finance/AccountTransactions";

export function FinanceTransactions() {
  const accounts = useAccounts();

  return (
    <div className="max-w-6xl">
      <h1 className="mb-6 text-2xl font-bold text-white">Transakcje</h1>
      {accounts.isLoading ? (
        <div className="flex justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-advisor-500 border-t-transparent" />
        </div>
      ) : accounts.isError ? (
        <p className="card text-sm text-red-400">Nie udało się pobrać kont.</p>
      ) : (
        <AccountTransactions accounts={accounts.data ?? []} />
      )}
    </div>
  );
}
