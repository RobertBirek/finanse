import { useSearchParams } from "react-router-dom";
import { TransactionSearch } from "../components/finance/TransactionSearch";
import { TransactionForm } from "../components/finance/TransactionForm";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { Dialog } from "../components/Dialog";

export function FinanceTransactions() {
  const [search, setSearch] = useSearchParams();
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
    <div className="max-w-6xl">
      <header className="finance-page-heading">
        <div>
          <h1>Transakcje</h1>
          <p>Historia, szczegóły i szybkie wyszukiwanie.</p>
        </div>
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
      </header>
      <FinanceTabs />
      <TransactionSearch />
      {open ? (
        <Dialog
          label="Dodaj transakcję"
          onClose={close}
          panelClassName="card w-full max-w-2xl"
        >
          <div className="mb-5 flex justify-between gap-4">
            <h2>Dodaj transakcję</h2>
            <button className="btn-secondary" onClick={close}>
              Zamknij formularz
            </button>
          </div>
          <TransactionForm initialType={create} onSuccess={close} />
        </Dialog>
      ) : null}
    </div>
  );
}
