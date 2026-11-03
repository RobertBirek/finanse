import type { Transaction } from "../../api/finance";
import { formatCalendarDate } from "../../lib/date";

export function TransactionDateLabel({
  transaction,
}: {
  transaction: Transaction;
}) {
  const meta = transaction.date_metadata;
  return (
    <>
      {meta?.purchase_date ? (
        <span className="block">
          Zakup: {formatCalendarDate(meta.purchase_date)}
        </span>
      ) : null}
      {meta?.booking_date ? (
        <span className="block">
          Księgowanie: {formatCalendarDate(meta.booking_date)}
        </span>
      ) : (
        <span className="block">
          {formatCalendarDate(transaction.transaction_date)} — typ daty
          nieustalony (historia)
        </span>
      )}
      {meta && !meta.purchase_date && transaction.type === "expense" ? (
        <span className="block">
          Data zakupu nieustalona — w analizie używamy daty księgowania.
        </span>
      ) : null}
    </>
  );
}

export function ExpenseDateBasis() {
  return (
    <p className="text-sm text-gray-400">
      Wydatki i budżety według daty zakupu. Gdy jej nie ustalono, używamy
      dotychczasowej daty transakcji. Historia konta i wyszukiwanie pozostają
      według daty księgowania lub nieoznaczonej daty historycznej.
    </p>
  );
}
