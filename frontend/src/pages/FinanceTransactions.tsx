import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BalanceReconciliation } from "../components/finance/BalanceReconciliation";
import { AccountStrip } from "../components/finance/AccountStrip";
import { TransactionSearch } from "../components/finance/TransactionSearch";
import { TransactionForm } from "../components/finance/TransactionForm";
import { Dialog } from "../components/Dialog";
import { PageHeader } from "../components/PageHeader";
import { IconButton } from "../components/IconButton";

export function FinanceTransactions() {
  const [search, setSearch] = useSearchParams();
  const [reconciling, setReconciling] = useState(false);
  const create = search.get("create");
  const open =
    create === "expense" ||
    create === "income" ||
    create === "transfer" ||
    create === "exchange";
  function close() {
    const next = new URLSearchParams(search);
    next.delete("create");
    setSearch(next, { replace: true, preventScrollReset: true });
  }
  return (
    <div className="page-workspace">
      <PageHeader
        title="Transakcje"
        description="Historia, szczegóły i szybkie wyszukiwanie."
        actions={
          <>
            <button
              className="btn-secondary"
              onClick={() => setReconciling(true)}
            >
              Uzgodnij saldo
            </button>
            <button
              className="btn-primary"
              onClick={() => {
                const next = new URLSearchParams(search);
                next.set("create", "expense");
                setSearch(next);
              }}
            >
              + Dodaj transakcję
            </button>
          </>
        }
      />
      <AccountStrip mode="filter" />
      <TransactionSearch />
      {reconciling && !open ? (
        <Dialog
          label="Uzgodnij saldo"
          onClose={() => setReconciling(false)}
          panelClassName="card w-full max-w-lg"
        >
          <h2>Uzgodnij saldo</h2>
          <BalanceReconciliation onHistory={() => setReconciling(false)} />
        </Dialog>
      ) : null}
      {open ? (
        <Dialog
          label="Dodaj transakcję"
          onClose={close}
          panelClassName="card w-full max-w-2xl"
        >
          <div className="mb-5 flex justify-between gap-4">
            <h2>Dodaj transakcję</h2>
            <IconButton
              icon="close"
              label="Zamknij formularz"
              onClick={close}
            />
          </div>
          <TransactionForm initialType={create} onSuccess={close} />
        </Dialog>
      ) : null}
    </div>
  );
}
